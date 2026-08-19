from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models import ImportItem, ImportRecord


YUPOO_IDENTITY_QUERY_IGNORES = {"uid", "referrercate", "issubcate", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "source"}
GENERIC_QUERY_IGNORES = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "source"}


@dataclass(frozen=True)
class ImportIdentity:
    namespace: str
    external_id: str
    normalized_url: str
    dedupe_key: str
    warnings: tuple[str, ...] = ()


@dataclass
class ImportIdentityCheck:
    status: str
    identity: ImportIdentity
    existing_item: ImportItem | None = None
    warnings: list[str] = field(default_factory=list)


def normalize_url_for_identity(url: str | None, *, yupoo: bool = False) -> str:
    if not url:
        return ""
    parsed = urlparse(str(url).strip())
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip()
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    port = f":{parsed.port}" if parsed.port and not ((scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)) else ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    ignored = YUPOO_IDENTITY_QUERY_IGNORES if yupoo else GENERIC_QUERY_IGNORES
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in ignored]
    return urlunparse((scheme, f"{host}{port}", path, "", urlencode(query, doseq=True), ""))


def is_yupoo_url(url: str | None) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower().rstrip(".")
    return host == "yupoo.com" or host.endswith(".yupoo.com") or host.endswith(".yupoo.com.cn")


def yupoo_album_id(url: str | None) -> str:
    parsed = urlparse(str(url or ""))
    parts = [part for part in parsed.path.split("/") if part]
    for index, part in enumerate(parts):
        if part == "albums" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def source_namespace(source: str | None, source_type: str | None, url: str | None) -> str:
    source_value = (source or "").strip().lower()
    source_type_value = (source_type or "").strip().lower()
    if source_value.startswith("spreadsheet/fansbuy"):
        return "spreadsheet/fansbuy"
    if source_value == "local_catalog":
        return "local_catalog"
    if source_type_value == "yupoo" or is_yupoo_url(url):
        return "yupoo"
    return source_value or source_type_value or "unknown"


def resolve_import_identity(*, source: str | None, source_type: str | None = None, external_id: str | None = None, source_url: str | None = None, normalized_source_url: str | None = None) -> ImportIdentity:
    raw_url = normalized_source_url or source_url or ""
    namespace = source_namespace(source, source_type, raw_url)
    yupoo = namespace == "yupoo"
    normalized_url = normalize_url_for_identity(raw_url, yupoo=yupoo)
    external = str(external_id or "").strip()
    warnings: list[str] = []
    if namespace == "yupoo":
        album_id = yupoo_album_id(normalized_url)
        host = (urlparse(normalized_url).hostname or "").lower().rstrip(".")
        if album_id and host:
            return ImportIdentity(namespace, album_id, normalized_url, f"yupoo:{host}:album:{album_id}")
        warnings.append("yupoo_album_identity_incomplete")
    if namespace == "spreadsheet/fansbuy":
        key = external or normalized_url
        return ImportIdentity(namespace, external, normalized_url, f"{namespace}:{key}", tuple(warnings))
    if namespace == "local_catalog":
        key = external or normalized_url
        return ImportIdentity(namespace, external, normalized_url, f"{namespace}:{key}", tuple(warnings))
    key = normalized_url or external
    if not normalized_url and external:
        warnings.append("external_id_without_source_url")
    return ImportIdentity(namespace, external, normalized_url, f"{namespace}:{key}", tuple(warnings))


def item_identity(item: ImportItem) -> ImportIdentity:
    record = item.import_record
    return resolve_import_identity(
        source=record.source if record else None,
        source_type=record.source_type if record else None,
        external_id=item.external_id,
        source_url=item.source_url,
        normalized_source_url=item.normalized_source_url,
    )


def find_existing_import_item(db: Session, identity: ImportIdentity, *, current_record_id: int | None = None) -> ImportIdentityCheck:
    filters = []
    if identity.external_id:
        filters.append(ImportItem.external_id == identity.external_id)
    if identity.normalized_url:
        filters.append(ImportItem.normalized_source_url == identity.normalized_url)
    if identity.namespace == "yupoo":
        album_id = yupoo_album_id(identity.normalized_url)
        if album_id:
            filters.append(ImportItem.normalized_source_url.like(f"%/albums/{album_id}%"))
            filters.append(ImportItem.source_url.like(f"%/albums/{album_id}%"))
    if not filters:
        return ImportIdentityCheck(status="new", identity=identity, warnings=list(identity.warnings))
    candidates = (
        db.query(ImportItem)
        .options(selectinload(ImportItem.import_record))
        .filter(or_(*filters))
        .all()
    )
    ambiguous_external = []
    for candidate in candidates:
        if current_record_id and candidate.import_record_id == current_record_id:
            continue
        candidate_identity = item_identity(candidate)
        if candidate_identity.dedupe_key == identity.dedupe_key:
            status = "exact_duplicate" if candidate.published_product_id else "same_source_existing"
            return ImportIdentityCheck(status=status, identity=identity, existing_item=candidate, warnings=list(identity.warnings))
        if identity.external_id and candidate.external_id == identity.external_id and candidate_identity.namespace == identity.namespace:
            return ImportIdentityCheck(status="conflicting_identity", identity=identity, existing_item=candidate, warnings=[*identity.warnings, "same_namespace_external_id_conflict"])
        if identity.external_id and candidate.external_id == identity.external_id:
            ambiguous_external.append(candidate)
    if ambiguous_external and not identity.normalized_url:
        return ImportIdentityCheck(status="manual_review", identity=identity, existing_item=ambiguous_external[0], warnings=[*identity.warnings, "external_id_reused_across_namespaces"])
    return ImportIdentityCheck(status="new", identity=identity, warnings=list(identity.warnings))
