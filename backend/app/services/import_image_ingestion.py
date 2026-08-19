from __future__ import annotations

import hashlib
import ipaddress
import shutil
import socket
import tempfile
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.exceptions import ApiError
from app.models import AdminUser, ImportImage, ImportItem, utc_now
from app.services.activities import record_activity
from app.services.http_security import TLS_ERROR_MESSAGE, build_verified_ssl_context, is_tls_verification_error
from app.services.import_review import ensure_not_stale, get_editable_record
from app.services.upload_storage import ensure_canonical_upload_write_allowed, remove_upload_storage_file
from app.services.url_security import is_blocked_ip as is_blocked_address
from app.services.url_security import normalize_hostname, normalized_netloc, parse_ipv4_numeric_literal, validate_url_authority
from app.utils.files import ensure_child_path

INGESTION_STATUSES = {"not_requested", "downloading", "validating", "stored", "failed", "skipped"}
ALLOWED_FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
ALLOWED_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
YUPOO_MEDIA_HOSTS = {"photo.yupoo.com", "photo.yupoo.com.cn", "pic.yupoo.com", "photo3.yupoo.com"}
SMALL_IMAGE_PIXELS = 20_000
READ_CHUNK_SIZE = 64 * 1024
AUTO_IMAGE_DOWNLOAD_CONCURRENCY = 1
DNS_RESOLVE_RETRY_DELAYS = (0.2, 0.5)


@dataclass
class IngestionReadiness:
    ready: bool
    blockers: list[str]
    warnings: list[str]


def selected_active_images(item: ImportItem) -> list[ImportImage]:
    return sorted([image for image in item.images if image.status == "active" and image.is_selected], key=lambda image: (image.position, image.id or 0))


def safe_source_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    netloc = normalized_netloc(parsed.hostname or "", parsed.port)
    return parsed._replace(netloc=netloc, query="", fragment="").geturl()[:300]


def is_blocked_ip(address: str) -> bool:
    return is_blocked_address(address)


def resolve_hostname(hostname: str) -> list[str]:
    hostname = normalize_hostname(hostname)
    numeric = parse_ipv4_numeric_literal(hostname)
    if numeric:
        return [numeric]
    try:
        ip = ipaddress.ip_address(hostname)
        return [str(ip)]
    except ValueError:
        pass
    last_error: socket.gaierror | None = None
    for attempt in range(len(DNS_RESOLVE_RETRY_DELAYS) + 1):
        try:
            info = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            break
        except socket.gaierror as exc:
            last_error = exc
            if attempt >= len(DNS_RESOLVE_RETRY_DELAYS):
                raise ApiError(422, "IMPORT_IMAGE_BLOCKED_HOST", "Nao foi possivel validar o host da imagem.", {"blocker": "blocked_host"}) from exc
            time.sleep(DNS_RESOLVE_RETRY_DELAYS[attempt])
    addresses = sorted({item[4][0] for item in info})
    if not addresses:
        raise ApiError(422, "IMPORT_IMAGE_BLOCKED_HOST", "Nao foi possivel validar o host da imagem.", {"blocker": "blocked_host"})
    return addresses


def validate_image_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ApiError(422, "IMPORT_IMAGE_INVALID_URL", "Imagem deve usar URL HTTP ou HTTPS valida.", {"blocker": "unsupported_scheme"})
    validate_url_authority(url, code="IMPORT_IMAGE_INVALID_URL", message="Imagem deve usar URL HTTP ou HTTPS valida.")
    host = normalize_hostname(parsed.hostname)
    for address in resolve_hostname(host):
        if is_blocked_ip(address):
            raise ApiError(422, "IMPORT_IMAGE_BLOCKED_IP", "A origem da imagem nao e permitida.", {"blocker": "blocked_ip"})
    return parsed._replace(netloc=normalized_netloc(host, parsed.port), fragment="").geturl()


def is_allowed_yupoo_media_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = normalize_hostname(hostname)
    return host in YUPOO_MEDIA_HOSTS


def validate_yupoo_media_url(url: str) -> str:
    cleaned = validate_image_url(url)
    parsed = urlparse(cleaned)
    if not is_allowed_yupoo_media_host(parsed.hostname):
        raise ApiError(422, "IMPORT_IMAGE_HOST_NOT_ALLOWED", "Host de midia Yupoo nao permitido.", {"blocker": "host_not_allowed"})
    return cleaned


def public_image_headers(*, referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/png,image/jpeg,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def ingestion_storage_root() -> Path:
    ensure_canonical_upload_write_allowed()
    root = Path(settings.upload_directory) / settings.import_image_storage_root.strip("/\\")
    root.mkdir(parents=True, exist_ok=True)
    return root


def product_storage_root(public_id: str) -> Path:
    ensure_canonical_upload_write_allowed()
    root = Path(settings.upload_directory) / "products" / public_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def relative_public_import_url(import_id: int, item_id: int, filename: str) -> str:
    prefix = settings.import_image_public_prefix.rstrip("/")
    return f"{prefix}/{import_id}/{item_id}/{filename}"


def image_path_from_storage_path(storage_path: str) -> Path:
    root = Path(settings.upload_directory)
    path = Path(storage_path)
    return ensure_child_path(root, path)


def stored_file_matches(image: ImportImage) -> bool:
    if not image.local_storage_path or not image.content_sha256:
        return False
    try:
        path = image_path_from_storage_path(image.local_storage_path)
    except ValueError:
        return False
    if not path.is_file():
        return False
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest() == image.content_sha256


def mark_image_ingestion_failed(db: Session, image: ImportImage, user: AdminUser, code: str) -> None:
    now = utc_now()
    image.ingestion_status = "failed"
    image.ingestion_finished_at = now
    image.ingestion_error = code[:120]
    image.ingested_by_id = user.id
    image.ingestion_metadata = {"error": code}
    record_activity(
        db,
        user_id=user.id,
        action="import_image_ingestion_failed",
        entity_type="import_image",
        entity_id=image.id,
        summary="Ingestao de imagem falhou.",
        metadata={"import_id": image.import_item.import_record_id, "item_id": image.import_item_id, "image_id": image.id, "result": code},
    )
    db.flush()


def fail_image_ingestion(db: Session, image: ImportImage, user: AdminUser, code: str, status_code: int = 422) -> None:
    mark_image_ingestion_failed(db, image, user, code)
    db.commit()
    raise ApiError(status_code, "IMPORT_IMAGE_INGESTION_FAILED", "Nao foi possivel armazenar esta imagem.", {"blocker": code})


def evaluate_ingestion_readiness(image: ImportImage) -> dict:
    blockers: list[str] = []
    warnings: list[str] = []
    if image.status != "active":
        blockers.append("image_not_active")
    if not image.is_selected:
        blockers.append("image_not_selected")
    if image.import_item.import_record.status not in {"draft", "scanning", "preview_ready"}:
        blockers.append("import_not_editable")
    if image.ingestion_status == "stored":
        if stored_file_matches(image):
            blockers.append("already_ingested")
        else:
            blockers.append("ingested_file_missing")
    try:
        validate_image_url(image.source_url)
    except ApiError as exc:
        blocker = exc.details.get("blocker") if isinstance(exc.details, dict) else None
        blockers.append(blocker or "invalid_source_url")
    if urlparse(image.source_url).scheme in {"http", "https"}:
        warnings.append("external_image")
    return {"ready": not blockers, "blockers": list(dict.fromkeys(blockers)), "warnings": list(dict.fromkeys(warnings))}


def ensure_ingestable(image: ImportImage, updated_at) -> None:
    ensure_not_stale(image.import_item, updated_at)
    readiness = evaluate_ingestion_readiness(image)
    blockers = [blocker for blocker in readiness["blockers"] if blocker != "already_ingested"]
    if blockers:
        raise ApiError(422, "IMPORT_IMAGE_NOT_READY_FOR_INGESTION", "Imagem nao esta pronta para ingestao.", {"blockers": blockers})


def validate_downloaded_image(path: Path, header_mime: str | None) -> tuple[str, int, int, list[str]]:
    warnings_list: list[str] = []
    Image.MAX_IMAGE_PIXELS = settings.import_image_max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                fmt = image.format
                image.load()
                width, height = image.size
    except Image.DecompressionBombWarning as exc:
        raise ApiError(422, "IMPORT_IMAGE_DECOMPRESSION_BOMB", "Imagem excede o limite seguro de pixels.", {"blocker": "decompression_bomb"}) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ApiError(415, "IMPORT_IMAGE_INVALID_SIGNATURE", "Assinatura real da imagem e invalida.", {"blocker": "invalid_image_signature"}) from exc
    if fmt not in ALLOWED_FORMAT_MIME:
        raise ApiError(415, "IMPORT_IMAGE_UNSUPPORTED_MIME", "Formato de imagem nao permitido.", {"blocker": "unsupported_mime_type"})
    mime = ALLOWED_FORMAT_MIME[fmt]
    if mime not in settings.import_image_allowed_mime_type_list:
        raise ApiError(415, "IMPORT_IMAGE_UNSUPPORTED_MIME", "Formato de imagem nao permitido.", {"blocker": "unsupported_mime_type"})
    if header_mime and header_mime not in settings.import_image_allowed_mime_type_list:
        raise ApiError(415, "IMPORT_IMAGE_UNSUPPORTED_MIME", "Formato de imagem nao permitido.", {"blocker": "unsupported_mime_type"})
    if header_mime and header_mime != mime:
        raise ApiError(415, "IMPORT_IMAGE_MIME_MISMATCH", "O MIME informado nao corresponde ao conteudo da imagem.", {"blocker": "unsupported_mime_type"})
    if width <= 0 or height <= 0 or width > settings.import_image_max_width or height > settings.import_image_max_height:
        raise ApiError(422, "IMPORT_IMAGE_INVALID_DIMENSIONS", "Dimensoes da imagem nao sao permitidas.", {"blocker": "invalid_dimensions"})
    if width * height > settings.import_image_max_pixels:
        raise ApiError(422, "IMPORT_IMAGE_DECOMPRESSION_BOMB", "Imagem excede o limite seguro de pixels.", {"blocker": "decompression_bomb"})
    if width * height < SMALL_IMAGE_PIXELS:
        warnings_list.append("small_image")
    return mime, width, height, warnings_list


def download_to_temp(client: httpx.Client, url: str, target_dir: Path, *, referer: str | None = None, yupoo_media_only: bool = False) -> tuple[Path, str, str | None, int]:
    current_url = validate_yupoo_media_url(url) if yupoo_media_only else validate_image_url(url)
    redirects = 0
    while True:
        with client.stream("GET", current_url, headers=public_image_headers(referer=referer)) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ApiError(502, "IMPORT_IMAGE_REDIRECT_INVALID", "Redirect sem destino valido.", {"blocker": "invalid_source_url"})
                redirects += 1
                if redirects > settings.import_image_max_redirects:
                    raise ApiError(310, "IMPORT_IMAGE_TOO_MANY_REDIRECTS", "Imagem excedeu o limite de redirects.", {"blocker": "too_many_redirects"})
                redirected = urljoin(current_url, location)
                current_url = validate_yupoo_media_url(redirected) if yupoo_media_only else validate_image_url(redirected)
                continue
            if response.status_code == 404:
                raise ApiError(404, "IMPORT_IMAGE_NOT_FOUND", "Origem da imagem nao encontrou o arquivo.", {"blocker": "source_not_found", "status_code": response.status_code})
            if response.status_code >= 500:
                raise ApiError(502, "IMPORT_IMAGE_SOURCE_ERROR", "Origem da imagem retornou erro temporario.", {"blocker": "source_error", "status_code": response.status_code})
            if response.status_code >= 400:
                raise ApiError(422, "IMPORT_IMAGE_SOURCE_REJECTED", "Origem da imagem recusou a requisicao.", {"blocker": "invalid_source_url", "status_code": response.status_code})
            header_mime = (response.headers.get("content-type") or "").split(";")[0].strip().lower() or None
            if header_mime and not header_mime.startswith("image/"):
                raise ApiError(415, "IMPORT_IMAGE_INVALID_CONTENT_TYPE", "A origem retornou conteudo que nao e imagem.", {"blocker": "invalid_content_type", "status_code": response.status_code, "content_type": header_mime})
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > settings.import_image_max_bytes:
                        raise ApiError(413, "IMPORT_IMAGE_TOO_LARGE", "Imagem excede o limite de bytes.", {"blocker": "content_too_large"})
                except ValueError:
                    raise ApiError(502, "IMPORT_IMAGE_SOURCE_ERROR", "Origem da imagem retornou cabecalhos invalidos.", {"blocker": "invalid_source_url"})
            hasher = hashlib.sha256()
            total = 0
            with tempfile.NamedTemporaryFile(prefix="import-image-", suffix=".part", dir=target_dir, delete=False) as handle:
                temp_path = Path(handle.name)
                try:
                    for chunk in response.iter_bytes(READ_CHUNK_SIZE):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > settings.import_image_max_bytes:
                            raise ApiError(413, "IMPORT_IMAGE_TOO_LARGE", "Imagem excede o limite de bytes.", {"blocker": "content_too_large"})
                        hasher.update(chunk)
                        handle.write(chunk)
                    handle.flush()
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
            if total <= 0:
                temp_path.unlink(missing_ok=True)
                raise ApiError(422, "IMPORT_IMAGE_EMPTY_FILE", "Imagem baixada esta vazia.", {"blocker": "empty_file", "status_code": response.status_code})
            return temp_path, hasher.hexdigest(), header_mime, total


def download_with_retries(client: httpx.Client, url: str, target_dir: Path, *, referer: str | None = None, yupoo_media_only: bool = False) -> tuple[Path, str, str | None, int]:
    last_error: Exception | None = None
    for attempt in range(settings.import_max_retries + 1):
        try:
            return download_to_temp(client, url, target_dir, referer=referer, yupoo_media_only=yupoo_media_only)
        except ApiError as exc:
            last_error = exc
            retryable_status = exc.status_code in {429, 500, 502, 503, 504}
            if not retryable_status or attempt >= settings.import_max_retries:
                raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            last_error = exc
            if attempt >= settings.import_max_retries:
                raise
        if settings.import_request_delay > 0:
            import time

            time.sleep(settings.import_request_delay)
    raise ApiError(504, "IMPORT_IMAGE_DOWNLOAD_FAILED", "Tempo limite ao armazenar imagem.", {"blocker": "download_failed"}) from last_error


def ingest_import_image(db: Session, *, import_id: int, item_id: int, image_id: int, updated_at, user: AdminUser, client_factory=None) -> dict:
    get_editable_record(db, import_id)
    query = db.query(ImportImage).options(selectinload(ImportImage.import_item).selectinload(ImportItem.import_record), selectinload(ImportImage.import_item).selectinload(ImportItem.images)).filter(ImportImage.id == image_id, ImportImage.import_item_id == item_id, ImportItem.id == item_id)
    query = query.join(ImportItem, ImportImage.import_item_id == ImportItem.id).filter(ImportItem.import_record_id == import_id)
    if db.bind and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    image = query.first()
    if not image:
        raise ApiError(404, "IMPORT_IMAGE_NOT_FOUND", "Imagem de importacao nao encontrada.")
    return store_import_image(db, image=image, updated_at=updated_at, user=user, client_factory=client_factory, commit_on_failure=True)


def store_import_image(db: Session, *, image: ImportImage, updated_at=None, user: AdminUser, client_factory=None, commit_on_failure: bool = False) -> dict:
    import_id = image.import_item.import_record_id
    item_id = image.import_item_id
    if image.ingestion_status == "stored" and stored_file_matches(image):
        record_activity(db, user_id=user.id, action="import_image_ingestion_idempotent", entity_type="import_image", entity_id=image.id, summary="Imagem ja estava ingerida.", metadata={"import_id": import_id, "item_id": item_id, "image_id": image.id, "result": "already_stored"})
        return {"image": image, "ready": True, "created": False, "message": "Esta imagem ja estava armazenada. Nenhum download duplicado foi realizado."}
    ensure_ingestable(image, updated_at)
    now = utc_now()
    image.ingestion_status = "downloading"
    image.ingestion_attempts += 1
    image.ingestion_started_at = now
    image.ingestion_finished_at = None
    image.ingested_by_id = user.id
    image.ingestion_error = None
    record_activity(db, user_id=user.id, action="import_image_ingestion_started", entity_type="import_image", entity_id=image.id, summary="Ingestao de imagem iniciada.", metadata={"import_id": import_id, "item_id": item_id, "image_id": image.id})
    db.flush()

    item_dir = ensure_child_path(ingestion_storage_root(), ingestion_storage_root() / str(import_id) / str(item_id))
    item_dir.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    final_path: Path | None = None
    final_path_created = False
    try:
        timeout = httpx.Timeout(connect=settings.import_image_connect_timeout, read=settings.import_image_read_timeout, write=settings.import_image_read_timeout, pool=settings.import_image_connect_timeout)
        factory = client_factory or (lambda: httpx.Client(timeout=timeout, follow_redirects=False, verify=build_verified_ssl_context()))
        with factory() as client:
            temp_path, content_hash, header_mime, size_bytes = download_with_retries(client, image.source_url, item_dir)
        image.ingestion_status = "validating"
        db.flush()
        mime, width, height, validation_warnings = validate_downloaded_image(temp_path, header_mime)
        filename = f"{content_hash}.{ALLOWED_EXTENSIONS[mime]}"
        final_path = ensure_child_path(item_dir, item_dir / filename)
        deduplicated = final_path.exists()
        if deduplicated:
            temp_path.unlink(missing_ok=True)
        else:
            shutil.move(str(temp_path), final_path)
            final_path_created = True
        image.ingestion_status = "stored"
        image.ingestion_finished_at = utc_now()
        image.ingestion_error = None
        image.local_filename = filename
        image.local_storage_path = str(final_path)
        image.local_public_url = relative_public_import_url(import_id, item_id, filename)
        image.local_mime_type = mime
        image.local_size_bytes = size_bytes
        image.local_width = width
        image.local_height = height
        image.content_sha256 = content_hash
        image.ingestion_metadata = {"source_url": safe_source_url_for_log(image.source_url), "warnings": validation_warnings, "deduplicated": deduplicated}
        if validation_warnings:
            existing = image.warnings or []
            image.warnings = list(dict.fromkeys([*existing, *validation_warnings]))
        record_activity(db, user_id=user.id, action="import_image_ingestion_finished", entity_type="import_image", entity_id=image.id, summary="Imagem armazenada com seguranca.", metadata={"import_id": import_id, "item_id": item_id, "image_id": image.id, "mime_type": mime, "size_bytes": size_bytes, "hash": content_hash, "result": "stored"})
        db.flush()
        return {"image": image, "ready": True, "created": True, "message": "Imagem armazenada com seguranca. O produto ainda nao foi publicado."}
    except ApiError as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if final_path_created and final_path:
            remove_upload_storage_file(final_path, context={"operation": "store_import_image", "image_id": image.id})
        blocker = exc.details.get("blocker") if isinstance(exc.details, dict) else None
        code = blocker or exc.code.lower()
        if commit_on_failure:
            fail_image_ingestion(db, image, user, code, exc.status_code)
        mark_image_ingestion_failed(db, image, user, code)
        raise ApiError(exc.status_code, "IMPORT_IMAGE_INGESTION_FAILED", "Nao foi possivel armazenar esta imagem.", {"blocker": code}) from exc
    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if final_path_created and final_path:
            remove_upload_storage_file(final_path, context={"operation": "store_import_image", "image_id": image.id})
        if is_tls_verification_error(exc):
            if commit_on_failure:
                fail_image_ingestion(db, image, user, "tls_verification_failed", 495)
            mark_image_ingestion_failed(db, image, user, "tls_verification_failed")
            raise ApiError(495, "IMPORT_IMAGE_TLS_VERIFICATION_FAILED", TLS_ERROR_MESSAGE, {"blocker": "tls_verification_failed"}) from exc
        if commit_on_failure:
            fail_image_ingestion(db, image, user, "download_failed", 504)
        mark_image_ingestion_failed(db, image, user, "download_failed")
        raise ApiError(504, "IMPORT_IMAGE_INGESTION_FAILED", "Nao foi possivel armazenar esta imagem.", {"blocker": "download_failed"})
    except OSError:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if final_path_created and final_path:
            remove_upload_storage_file(final_path, context={"operation": "store_import_image", "image_id": image.id})
        if commit_on_failure:
            fail_image_ingestion(db, image, user, "storage_error", 500)
        mark_image_ingestion_failed(db, image, user, "storage_error")
        raise ApiError(500, "IMPORT_IMAGE_INGESTION_FAILED", "Nao foi possivel armazenar esta imagem.", {"blocker": "storage_error"})
    except Exception:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if final_path_created and final_path:
            remove_upload_storage_file(final_path, context={"operation": "store_import_image", "image_id": image.id})
        raise


def ingest_import_item_images(db: Session, *, item: ImportItem, user: AdminUser, client_factory=None) -> dict:
    images = selected_active_images(item)[: settings.import_image_max_per_item]
    result = {"attempted": 0, "stored": 0, "failed": 0, "skipped": 0, "errors": []}
    for image in images:
        if image.ingestion_status == "stored" and stored_file_matches(image):
            result["skipped"] += 1
            continue
        result["attempted"] += 1
        try:
            stored = store_import_image(db, image=image, user=user, client_factory=client_factory, commit_on_failure=False)
            if stored["created"]:
                result["stored"] += 1
            else:
                result["skipped"] += 1
        except ApiError as exc:
            result["failed"] += 1
            blocker = exc.details.get("blocker") if isinstance(exc.details, dict) else exc.code
            result["errors"].append({"image_id": image.id, "error": blocker})
    choose_import_item_cover(item)
    return result


def choose_import_item_cover(item: ImportItem) -> None:
    ordered = sorted(item.images, key=lambda image: (image.position, image.id or 0))
    valid = [
        image
        for image in ordered
        if image.status == "active"
        and image.is_selected
        and image.ingestion_status == "stored"
        and stored_file_matches(image)
    ]
    if not valid:
        for image in ordered:
            image.is_cover = False
        return
    current = next((image for image in valid if image.is_cover), None)
    cover = current or valid[0]
    for image in ordered:
        image.is_cover = image.id == cover.id


def remove_import_image_files(import_id: int) -> list[str]:
    root = ingestion_storage_root()
    import_dir = ensure_child_path(root, root / str(import_id))
    removed: list[str] = []
    if not import_dir.exists():
        return removed
    for path in sorted(import_dir.rglob("*"), reverse=True):
        safe_path = ensure_child_path(import_dir, path)
        if safe_path.is_file():
            safe_path.unlink(missing_ok=True)
            removed.append(str(safe_path))
        elif safe_path.is_dir():
            try:
                safe_path.rmdir()
            except OSError:
                pass
    try:
        import_dir.rmdir()
    except OSError:
        pass
    return removed


def ingest_selected_images(db: Session, *, import_id: int, item_id: int, image_ids: list[int], updated_at, user: AdminUser, client_factory=None) -> list[ImportImage]:
    if len(image_ids) > settings.import_image_max_per_request:
        raise ApiError(422, "IMPORT_IMAGE_BATCH_LIMIT", "Limite de imagens por acao excedido.", {"limit": settings.import_image_max_per_request})
    item = db.query(ImportItem).options(selectinload(ImportItem.images), selectinload(ImportItem.import_record)).filter(ImportItem.id == item_id, ImportItem.import_record_id == import_id).first()
    if not item:
        raise ApiError(404, "IMPORT_ITEM_NOT_FOUND", "Item de importacao nao encontrado.")
    ensure_not_stale(item, updated_at)
    allowed = {image.id for image in selected_active_images(item)}
    if any(image_id not in allowed for image_id in image_ids):
        raise ApiError(422, "IMPORT_IMAGE_SELECTION_INVALID", "A lista contem imagem fora da selecao ativa.")
    result = []
    for current_image_id in image_ids:
        result.append(ingest_import_image(db, import_id=import_id, item_id=item_id, image_id=current_image_id, updated_at=None, user=user, client_factory=client_factory)["image"])
    return result
