from time import time

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_csrf
from app.exceptions import ApiError
from app.models import AdminUser, utc_now
from app.schemas.auth import CsrfRead, LoginRequest, SessionRead
from app.schemas.user import UserRead
from app.security import DUMMY_PASSWORD_HASH, create_session_payload, get_csrf, normalize_email, sign_session, verify_password
from app.services.activities import record_activity
from app.utils.client_ip import get_client_ip

router = APIRouter()
attempts: dict[str, list[float]] = {}
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 10 * 60
LOGIN_RATE_LIMIT_MAX_FAILURES = 5
LOGIN_RATE_LIMIT_MAX_KEYS = 1000


def client_ip(request: Request) -> str:
    return get_client_ip(request)


def prune_attempts(now: float):
    for key, values in list(attempts.items()):
        recent = [item for item in values if now - item < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
        if recent:
            attempts[key] = recent
        else:
            attempts.pop(key, None)
    if len(attempts) <= LOGIN_RATE_LIMIT_MAX_KEYS:
        return
    oldest_keys = sorted(attempts, key=lambda key: attempts[key][0] if attempts[key] else 0)
    for key in oldest_keys[: len(attempts) - LOGIN_RATE_LIMIT_MAX_KEYS]:
        attempts.pop(key, None)


def check_rate_limit(key: str, *, now: float | None = None):
    now = time() if now is None else now
    prune_attempts(now)
    recent = [item for item in attempts.get(key, []) if now - item < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
    attempts[key] = recent
    if len(recent) >= LOGIN_RATE_LIMIT_MAX_FAILURES:
        raise ApiError(429, "LOGIN_RATE_LIMITED", "Muitas tentativas. Tente novamente mais tarde.")


def record_failed_login(key: str, *, now: float | None = None):
    now = time() if now is None else now
    prune_attempts(now)
    recent = [item for item in attempts.get(key, []) if now - item < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
    recent.append(now)
    attempts[key] = recent


def clear_failed_login(key: str):
    attempts.pop(key, None)


def rate_limit_key(request: Request, email: str) -> str:
    return f"{client_ip(request)}:{email}"


@router.post("/login", response_model=SessionRead)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = normalize_email(payload.email)
    key = rate_limit_key(request, email)
    check_rate_limit(key)
    user = db.query(AdminUser).filter(AdminUser.email == email).first()
    password_ok = verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not user.is_active or not password_ok:
        record_failed_login(key)
        raise ApiError(401, "INVALID_CREDENTIALS", "E-mail ou senha inválidos.")
    clear_failed_login(key)
    session_payload = create_session_payload(user.id, user.session_version)
    response.set_cookie(
        request.app.state.settings.session_cookie_name,
        sign_session(session_payload),
        max_age=request.app.state.settings.session_max_age,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite=request.app.state.settings.cookie_samesite,
        path="/",
    )
    user.last_login_at = utc_now()
    record_activity(db, user_id=user.id, action="login", summary="Login administrativo.", ip_address=client_ip(request))
    return SessionRead(authenticated=True, user=UserRead.model_validate(user))


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, user: AdminUser = Depends(current_user), db: Session = Depends(get_db)):
    response.delete_cookie(
        request.app.state.settings.session_cookie_name,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        samesite=request.app.state.settings.cookie_samesite,
    )
    record_activity(db, user_id=user.id, action="logout", summary="Logout administrativo.", ip_address=client_ip(request))
    return {"message": "Sessão encerrada."}


@router.get("/session", response_model=SessionRead)
def session(user: AdminUser = Depends(current_user)):
    return SessionRead(authenticated=True, user=UserRead.model_validate(user))


@router.get("/csrf", response_model=CsrfRead)
def csrf(request: Request, user: AdminUser = Depends(current_user)):
    from app.dependencies import get_session_payload

    token = get_csrf(get_session_payload(request))
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "Sessão inválida ou expirada.")
    return CsrfRead(csrf_token=token)
