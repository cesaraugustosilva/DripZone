from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_CORS_ORIGINS = (
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:4199",
    "http://localhost:4199",
)


class Settings(BaseSettings):
    app_name: str = "DripZone Admin API"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 3000
    app_debug: bool = True
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./storage/database/dripzone.db"
    session_secret_key: str = "change-this-local-development-secret"
    session_cookie_name: str = "dripzone_admin_session"
    session_max_age: int = 28800
    session_cookie_samesite: str = "lax"
    cors_origins: str = "http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:4199,http://localhost:4199"
    upload_directory: str = "storage/uploads"
    public_products_path: str = ""
    log_level: str = "INFO"
    max_upload_size: int = 5 * 1024 * 1024
    allowed_image_types: str = "image/jpeg,image/png,image/webp"
    import_image_max_bytes: int = 10 * 1024 * 1024
    import_image_connect_timeout: float = 5.0
    import_image_read_timeout: float = 15.0
    import_image_max_redirects: int = 3
    import_image_allowed_mime_types: str = "image/jpeg,image/png,image/webp"
    import_image_max_width: int = 12000
    import_image_max_height: int = 12000
    import_image_max_pixels: int = 40_000_000
    import_image_storage_root: str = "imports"
    import_image_public_prefix: str = "/uploads/imports"
    import_image_max_per_item: int = 12
    import_image_max_per_request: int = 20
    import_allowed_hosts: str = "example.com,www.example.com,yupoo.com,www.yupoo.com"
    import_allowed_domains: str = "yupoo.com"
    import_max_pages: int = 5
    import_max_items: int = 50
    import_request_timeout: float = 10.0
    import_request_delay: float = 0.2
    import_max_retries: int = 2
    import_max_response_bytes: int = 2 * 1024 * 1024
    import_user_agent: str = "DripZoneImportPreview/1.0"
    version: str = "1.0.0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.app_env != "production":
            return self
        errors: list[str] = []
        if self.app_debug:
            errors.append("APP_DEBUG deve ser false em producao.")
        if self.database_url.startswith("sqlite"):
            errors.append("DATABASE_URL de producao deve apontar para PostgreSQL.")
        if self.session_secret_key == "change-this-local-development-secret" or len(self.session_secret_key) < 32:
            errors.append("SESSION_SECRET_KEY de producao deve ser unico e ter pelo menos 32 caracteres.")
        if not self.cors_origin_list:
            errors.append("CORS_ORIGINS deve listar ao menos uma origem de producao.")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origin_list):
            errors.append("CORS_ORIGINS de producao nao deve conter localhost por padrao.")
        if self.session_cookie_samesite.lower() not in {"lax", "strict", "none"}:
            errors.append("SESSION_COOKIE_SAMESITE deve ser lax, strict ou none.")
        if errors:
            raise ValueError("Configuracao de producao invalida: " + " ".join(errors))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        origins: list[str] = []
        if self.app_env in {"development", "test"}:
            origins.extend(DEVELOPMENT_CORS_ORIGINS)
        for origin in self.cors_origins.split(","):
            cleaned = origin.strip()
            if cleaned and cleaned != "*" and cleaned not in origins:
                origins.append(cleaned)
        return origins

    @property
    def allowed_image_type_list(self) -> list[str]:
        return [mime.strip() for mime in self.allowed_image_types.split(",") if mime.strip()]

    @property
    def import_image_allowed_mime_type_list(self) -> list[str]:
        return [mime.strip() for mime in self.import_image_allowed_mime_types.split(",") if mime.strip()]

    @property
    def import_allowed_host_list(self) -> list[str]:
        return [host.strip().lower() for host in self.import_allowed_hosts.split(",") if host.strip()]

    @property
    def import_allowed_domain_list(self) -> list[str]:
        return [domain.strip().lower().rstrip(".") for domain in self.import_allowed_domains.split(",") if domain.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_directory)

    @property
    def cookie_secure(self) -> bool:
        return self.app_env not in {"development", "test"}

    @property
    def cookie_samesite(self) -> str:
        return self.session_cookie_samesite.lower()

    @property
    def public_products_file(self) -> Path | None:
        return Path(self.public_products_path) if self.public_products_path.strip() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
