from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.config import settings


SESSION_USER_KEY = "user_id"
SESSION_VERSION_KEY = "session_version"
SESSION_CSRF_KEY = "csrf"
EMAIL_ADAPTER = TypeAdapter(EmailStr)
DUMMY_PASSWORD_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEe.8qQh4U5pP6mAxpZRl76IrxWJCXRc8dm"


def password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_auth_email(email: str) -> str:
    normalized = normalize_email(email)
    try:
        EMAIL_ADAPTER.validate_python(normalized)
    except ValidationError as exc:
        raise ValueError("E-mail invalido.") from exc
    return normalized


def validate_password_strength(
    password: str,
    confirmation: str,
    *,
    email: str | None = None,
    name: str | None = None,
    current_hash: str | None = None,
) -> None:
    if password != confirmation:
        raise ValueError("As senhas nao conferem.")
    if len(password) > 200:
        raise ValueError("A senha deve ter no maximo 200 caracteres.")
    folded_password = password.strip().casefold()
    if email and folded_password == normalize_email(email).casefold():
        raise ValueError("A senha nao pode ser igual ao e-mail.")
    if name and folded_password == name.strip().casefold():
        raise ValueError("A senha nao pode ser igual ao nome do administrador.")
    checks = [
        (len(password) >= 12, "A senha deve ter pelo menos 12 caracteres."),
        (any(char.isupper() for char in password), "A senha deve ter pelo menos uma letra maiuscula."),
        (any(char.islower() for char in password), "A senha deve ter pelo menos uma letra minuscula."),
        (any(char.isdigit() for char in password), "A senha deve ter pelo menos um numero."),
        (any(not char.isalnum() for char in password), "A senha deve ter pelo menos um caractere especial."),
    ]
    for valid, message in checks:
        if not valid:
            raise ValueError(message)
    if current_hash and verify_password(password, current_hash):
        raise ValueError("A nova senha nao pode ser igual a senha atual.")


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret_key, salt="dripzone-admin-session")


def create_session_payload(user_id: int, session_version: int) -> dict[str, Any]:
    return {
        SESSION_USER_KEY: user_id,
        SESSION_VERSION_KEY: session_version,
        SESSION_CSRF_KEY: token_urlsafe(32),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def sign_session(payload: dict[str, Any]) -> str:
    return serializer().dumps(payload)


def load_session(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        return serializer().loads(value, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None


def get_csrf(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    token = payload.get(SESSION_CSRF_KEY)
    return token if isinstance(token, str) else None
