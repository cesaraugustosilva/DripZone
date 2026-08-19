import logging
from pathlib import Path
import os

from app.config import settings
from app.database import is_sqlite_url
from app.exceptions import ApiError
from app.utils.files import ensure_child_path


CANONICAL_DOCKER_UPLOAD_DIRECTORY = Path("/app/storage/uploads")
ALLOW_HOST_UPLOAD_WRITES_ENV = "DRIPZONE_ALLOW_HOST_UPLOAD_WRITES"
logger = logging.getLogger(__name__)


def resolved_upload_directory() -> Path:
    return Path(settings.upload_directory).expanduser().resolve()


def is_canonical_docker_upload_directory(path: Path | None = None) -> bool:
    raw = str(settings.upload_directory).replace("\\", "/").rstrip("/")
    if raw == "/app/storage/uploads":
        return True
    candidate = (path or resolved_upload_directory())
    try:
        return candidate == CANONICAL_DOCKER_UPLOAD_DIRECTORY
    except OSError:
        return False


def ensure_canonical_upload_write_allowed() -> None:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if is_sqlite_url(settings.database_url):
        return
    if is_canonical_docker_upload_directory():
        return
    if os.getenv(ALLOW_HOST_UPLOAD_WRITES_ENV) == "1":
        return
    raise ApiError(
        409,
        "UPLOAD_STORAGE_NOT_CANONICAL",
        "Refusing to write product uploads from host mode while Docker storage is canonical.",
        {
            "expected_upload_directory": str(CANONICAL_DOCKER_UPLOAD_DIRECTORY),
            "actual_upload_directory": str(resolved_upload_directory()),
        },
    )


def safe_upload_storage_path(storage_path: str | Path) -> Path:
    return ensure_child_path(resolved_upload_directory(), Path(storage_path))


def remove_upload_storage_file(storage_path: str | Path, *, context: dict | None = None) -> bool:
    try:
        path = safe_upload_storage_path(storage_path)
    except ValueError:
        logger.warning("upload_delete_blocked_outside_root", extra={"storage_path": str(storage_path), "context": context or {}})
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        logger.exception("upload_delete_failed", extra={"storage_path": str(path), "context": context or {}})
        raise ApiError(
            500,
            "UPLOAD_DELETE_FAILED",
            "Registro atualizado, mas nao foi possivel remover o arquivo fisico de upload.",
            {"storage_path": str(path), "context": context or {}, "recoverable": True},
        ) from exc
