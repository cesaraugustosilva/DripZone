from collections.abc import Iterable

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import ApiError
from app.models import AdminUser
from app.security import SESSION_USER_KEY, SESSION_VERSION_KEY, get_csrf, load_session


def get_session_payload(request: Request) -> dict | None:
    return load_session(request.cookies.get(request.app.state.settings.session_cookie_name))


def current_user(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    payload = get_session_payload(request)
    user_id = payload.get(SESSION_USER_KEY) if payload else None
    if not user_id:
        raise ApiError(401, "UNAUTHORIZED", "Sessão inválida ou expirada.")
    user = db.get(AdminUser, int(user_id))
    if not user or not user.is_active:
        raise ApiError(401, "UNAUTHORIZED", "Sessão inválida ou expirada.")
    if payload.get(SESSION_VERSION_KEY) != user.session_version:
        raise ApiError(401, "UNAUTHORIZED", "Sessão inválida ou expirada.")
    return user


def require_roles(*roles: str):
    def checker(user: AdminUser = Depends(current_user)) -> AdminUser:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Permissão insuficiente.")
        return user

    return checker


def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    payload = get_session_payload(request)
    expected = get_csrf(payload)
    if not expected or not x_csrf_token or not secrets_compare(expected, x_csrf_token):
        raise ApiError(403, "CSRF_INVALID", "Token CSRF inválido ou ausente.")


def secrets_compare(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    result = 0
    for a, b in zip(left.encode(), right.encode(), strict=True):
        result |= a ^ b
    return result == 0
