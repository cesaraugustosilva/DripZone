import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_settings_require_secure_defaults():
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="production",
            app_debug=True,
            database_url="sqlite:///./storage/database/dripzone.db",
            cors_origins="http://127.0.0.1:4173",
            session_secret_key="change-this-local-development-secret",
        )

    message = str(exc.value)
    assert "APP_DEBUG deve ser false" in message
    assert "PostgreSQL" in message
    assert "SESSION_SECRET_KEY" in message
    assert "localhost" in message


def test_production_settings_accept_explicit_origin_and_secure_cookie():
    settings = Settings(
        app_env="production",
        app_debug=False,
        database_url="postgresql+psycopg://dripzone:secret@postgres:5432/dripzone",
        cors_origins="https://dripzone.com.br",
        session_secret_key="a-production-secret-with-more-than-32-chars",
    )

    assert settings.cors_origin_list == ["https://dripzone.com.br"]
    assert settings.cookie_secure is True
    assert settings.cookie_samesite == "lax"
