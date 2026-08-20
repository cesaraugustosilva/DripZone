import hashlib
import html
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import ApiError
from app.models import AdminUser, Brand, Category, ImportItem, ImportRecord, utc_now
from app.services.http_security import TLS_ERROR_MESSAGE, build_verified_ssl_context, is_tls_verification_error
from app.services.url_security import is_blocked_ip, normalize_hostname, normalized_netloc, resolve_public_hostname, validate_url_authority
from app.services.import_identity import find_existing_import_item, resolve_import_identity
from app.services.import_rules import CATEGORY_RULES, COLOR_RULES, CONFIDENCE_WEIGHTS, IGNORED_IMAGE_TERMS, KNOWN_MODELS, MAX_IMAGES_PER_ITEM, NAME_NOISE_TERMS
from app.utils.slug import slugify

logger = logging.getLogger(__name__)

ACTIVE_IMPORT_STATUSES = {"draft", "scanning", "preview_ready"}
FINAL_PREVIEW_STATUS = "preview_ready"
ITEM_STATUSES = {"pending", "duplicate", "needs_review", "invalid", "reviewed"}
IGNORED_QUERY_PREFIXES = ("utm_",)
IGNORED_QUERY_KEYS = {"fbclid", "gclid", "ref", "source"}
PAGE_QUERY_KEYS = {"page", "p", "page_no", "pageNo"}
READ_CHUNK_SIZE = 64 * 1024


class Fetcher(Protocol):
    def get(self, url: str) -> "FetchedPage":
        ...


@dataclass
class FetchedPage:
    url: str
    body: str
    content_type: str
    status_code: int


@dataclass
class CandidateItem:
    source_url: str
    title: str
    image_urls: list[str]
    page_number: int
    position: int
    raw_metadata: dict


@dataclass
class ImportScanState:
    pages_to_visit: list[str]
    visited_pages: set[str]
    queued_pages: set[str]
    seen_item_keys: set[str]
    pages_read: int = 0
    raw_items_found: int = 0
    unique_items_found: int = 0
    duplicate_items_removed: int = 0
    processed_items: int = 0
    truncated: bool = False
    pagination_truncated: bool = False
    limit_reason: str | None = None
    last_page_processed: str | None = None


@dataclass
class YupooAlbumLink:
    source_url: str
    title: str
    thumbnail_url: str | None
    position: int


@dataclass
class YupooAlbumProduct:
    source_url: str
    title: str
    description: str
    image_urls: list[str]
    image_alts: list[str]


YUPOO_PAGINATION_FALLBACK_LIMIT = 500
YUPOO_IMAGE_ATTR_PRIORITY = ("data-origin-src", "data-original", "data-src", "src")


class ImportHTMLParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__()
        self.page_url = page_url
        self.title_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.images: list[dict] = []
        self._in_title = False
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        data = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            self._anchor_href = data.get("href")
            self._anchor_text = []
        elif tag == "img":
            src = data.get("src") or data.get("data-src") or data.get("data-original")
            if src:
                self.images.append(
                    {
                        "src": urljoin(self.page_url, src),
                        "alt": data.get("alt", "").strip(),
                        "title": data.get("title", "").strip(),
                        "class": data.get("class", "").strip(),
                        "id": data.get("id", "").strip(),
                        "width": data.get("width", "").strip(),
                        "height": data.get("height", "").strip(),
                    }
                )

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor_href:
            self.links.append((urljoin(self.page_url, self._anchor_href), " ".join(self._anchor_text).strip()))
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str):
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._anchor_href:
            self._anchor_text.append(text)


class YupooHTMLParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__()
        self.page_url = page_url
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.album_links: list[YupooAlbumLink] = []
        self.gallery_images: list[dict] = []
        self.pagination_links: list[str] = []
        self.page_text_parts: list[str] = []
        self._in_title = False
        self._current_album_href: str | None = None
        self._current_album_title: str = ""
        self._current_album_thumbnail: str | None = None
        self._current_album_position = 0

    def handle_starttag(self, tag: str, attrs):
        data = {name.lower(): html.unescape(value or "") for name, value in attrs}
        classes = set((data.get("class") or "").split())
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = data.get("property") or data.get("name")
            content = data.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()
        elif tag == "a":
            href = data.get("href")
            if not href:
                return
            absolute = urljoin(self.page_url, href)
            if "album__main" in classes and is_yupoo_album_url(absolute):
                self._current_album_href = absolute
                self._current_album_title = data.get("title", "").strip()
                self._current_album_thumbnail = None
            elif "pagination__number" in classes or "pagination__button" in classes:
                if is_yupoo_listing_url(absolute):
                    self.pagination_links.append(normalize_url(absolute))
        elif tag == "input":
            if (data.get("name") or "").casefold() in {key.casefold() for key in PAGE_QUERY_KEYS}:
                for page_url in pagination_urls_from_max_control(self.page_url, data.get("max")):
                    self.pagination_links.append(page_url)
        elif tag == "img":
            src = best_yupoo_image_source(data)
            if not src:
                return
            absolute_src = urljoin(self.page_url, src)
            if self._current_album_href and ("album__img" in classes or "autocover" in classes):
                self._current_album_thumbnail = prefer_yupoo_image_resolution(absolute_src)
            if data.get("data-type") == "photo" and data.get("data-photoindex") is not None:
                self.gallery_images.append(
                    {
                        "src": prefer_yupoo_image_resolution(absolute_src),
                        "raw_src": absolute_src,
                        "source_attr": next((attr for attr in YUPOO_IMAGE_ATTR_PRIORITY if data.get(attr) == src), ""),
                        "alt": data.get("alt", "").strip(),
                        "title": data.get("title", "").strip(),
                        "class": data.get("class", "").strip(),
                        "id": data.get("id", "").strip(),
                        "position": data.get("data-photoindex", "").strip(),
                    }
                )

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_album_href:
            self._current_album_position += 1
            self.album_links.append(
                YupooAlbumLink(
                    normalize_url(self._current_album_href),
                    self._current_album_title.strip(),
                    self._current_album_thumbnail,
                    self._current_album_position,
                )
            )
            self._current_album_href = None
            self._current_album_title = ""
            self._current_album_thumbnail = None

    def handle_data(self, data: str):
        text = data.strip()
        if text and self._in_title:
            self.title_parts.append(text)
        if text:
            self.page_text_parts.append(text)


def is_yupoo_category_url(url: str) -> bool:
    return re.search(r"/categories/\d+(?:[/?#]|$)", urlparse(str(url)).path + "?", flags=re.I) is not None


def is_yupoo_collection_url(url: str) -> bool:
    return re.search(r"/collections/\d+(?:[/?#]|$)", urlparse(str(url)).path + "?", flags=re.I) is not None


def is_yupoo_album_url(url: str) -> bool:
    return re.search(r"/albums/\d+(?:[/?#]|$)", urlparse(str(url)).path + "?", flags=re.I) is not None


def is_yupoo_albums_index_url(url: str) -> bool:
    path = urlparse(str(url)).path.rstrip("/") or "/"
    return path in {"/", "/albums"}


def is_yupoo_listing_url(url: str) -> bool:
    return is_yupoo_category_url(url) or is_yupoo_collection_url(url) or is_yupoo_albums_index_url(url)


def detect_yupoo_page_type(url: str, html_body: str | None = None) -> str:
    if is_yupoo_category_url(url):
        return "category_page"
    if is_yupoo_collection_url(url):
        return "collection_page"
    if is_yupoo_album_url(url):
        return "album_page"
    body = html_body or ""
    if 'class="album__main"' in body or "class='album__main'" in body:
        return "listing_page"
    if "showalbum.css" in body or "viewer__thumbnail" in body:
        return "album_page"
    return "unsupported_page"


GLOBAL_TITLE_TERMS = {
    "supplier product catalog",
    "category",
    "album",
    "home",
    "all categories",
    "分类",
    "相册",
    "又拍图片管家",
}


def clean_yupoo_title(value: str | None, *, owner: str | None = None, category_title: str | None = None) -> str:
    raw = html.unescape(value or "").replace("$nbsp", " ")
    parts = [re.sub(r"\s+", " ", part).strip() for part in raw.split("|")]
    owner_norm = normalize_product_text(owner)
    category_norm = normalize_product_text(category_title)
    global_terms = {term for term in (normalize_product_text(item) for item in GLOBAL_TITLE_TERMS) if term}
    cleaned_parts = []
    for part in parts:
        normalized = normalize_product_text(part)
        if not normalized:
            continue
        if normalized in global_terms:
            continue
        if owner_norm and normalized == owner_norm:
            continue
        if category_norm and normalized == category_norm:
            continue
        cleaned_parts.append(part)
    candidate = cleaned_parts[0] if cleaned_parts else ""
    if is_global_yupoo_title(candidate, owner=owner, category_title=category_title):
        return ""
    return candidate[:300]


def is_global_yupoo_title(value: str | None, *, owner: str | None = None, category_title: str | None = None) -> bool:
    normalized = normalize_product_text(value)
    if not normalized:
        return True
    global_terms = [term for term in (normalize_product_text(item) for item in GLOBAL_TITLE_TERMS) if term]
    if any(term in normalized for term in global_terms):
        return True
    if owner and normalized == normalize_product_text(owner):
        return True
    if category_title and normalized == normalize_product_text(category_title):
        return True
    return False


def prefer_yupoo_image_resolution(url: str) -> str:
    parsed = urlparse(str(url))
    if "photo.yupoo.com" not in (parsed.hostname or ""):
        return url
    path = re.sub(r"/(?:small|square|thumb)\.(jpg|jpeg|png|webp)$", r"/medium.\1", parsed.path, flags=re.I)
    return urlunparse(parsed._replace(path=path, fragment=""))


def best_yupoo_image_source(attrs: dict[str, str]) -> str:
    for key in YUPOO_IMAGE_ATTR_PRIORITY:
        value = attrs.get(key)
        if value:
            return value
    return ""


def pagination_urls_from_max_control(page_url: str, raw_max: str | None) -> list[str]:
    try:
        page_max = int(str(raw_max or "").strip())
    except ValueError:
        return []
    if page_max <= 1:
        return []
    page_max = min(page_max, YUPOO_PAGINATION_FALLBACK_LIMIT)
    current = page_number_from_url(page_url) or 1
    return [category_page_url(page_url, page) for page in range(1, page_max + 1) if page != current]


def parse_yupoo_page(url: str, html_body: str) -> tuple[str, dict[str, str], list[YupooAlbumLink], list[dict], list[str]]:
    parser = YupooHTMLParser(url)
    parser.feed(html_body)
    title = " ".join(parser.title_parts).strip()
    meta = dict(parser.meta)
    page_text = re.sub(r"\s+", " ", " ".join(parser.page_text_parts)).strip()
    if page_text:
        meta["page_text"] = page_text[:8000]
    return title, meta, parser.album_links, parser.gallery_images, parser.pagination_links


def discover_yupoo_album_links(root_url: str, page_url: str, html_body: str) -> tuple[list[YupooAlbumLink], list[str], dict]:
    page_title, _, album_links, _, pagination_links = parse_yupoo_page(page_url, html_body)
    valid_links: list[YupooAlbumLink] = []
    seen: set[str] = set()
    before = len(album_links)
    for item in album_links:
        try:
            normalized = normalize_url(item.source_url)
            if not is_yupoo_album_url(normalized):
                continue
            if urlparse(normalized).netloc != urlparse(normalize_url(root_url)).netloc:
                continue
            dedupe_key = item_dedupe_key_for_import(normalized, source="folder_preview", source_type="yupoo")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            valid_links.append(YupooAlbumLink(normalized, clean_yupoo_title(item.title), item.thumbnail_url, item.position))
        except Exception:
            continue
    scoped_pages = [page for page in pagination_links if is_same_yupoo_category_page(page, root_url)]
    return valid_links, list(dict.fromkeys(scoped_pages)), {"page_title": page_title, "albums_found_before_dedupe": before, "albums_valid": len(valid_links), "albums_duplicates_removed": before - len(valid_links)}


def extract_yupoo_album_product(page_url: str, html_body: str, *, fallback_title: str = "", category_title: str = "") -> YupooAlbumProduct:
    if detect_yupoo_page_type(page_url, html_body) == "category_page":
        raise ApiError(422, "IMPORT_YUPOO_CATEGORY_AS_PRODUCT", "Pagina de categoria nao pode ser extraida como produto.")
    page_title, meta, _, gallery_images, _ = parse_yupoo_page(page_url, html_body)
    owner = owner_from_yupoo_page(html_body)
    title = (
        clean_yupoo_title(page_title, owner=owner, category_title=category_title)
        or clean_yupoo_title(meta.get("og:title"), owner=owner, category_title=category_title)
        or clean_yupoo_title(fallback_title, owner=owner, category_title=category_title)
        or folder_name_from_url(page_url)
    )
    description = re.sub(r"\s+-\s+Supplier Product Catalog\s*$", "", html.unescape(meta.get("description") or meta.get("og:description") or "")).strip()
    ordered = sorted(gallery_images, key=lambda image: int(image.get("position") or 0))
    deduped: list[dict] = []
    seen_media: set[str] = set()
    for image in ordered:
        src = image.get("src")
        if not src or is_ignored_yupoo_gallery_image(image):
            continue
        key = yupoo_media_key(src)
        if key in seen_media:
            continue
        seen_media.add(key)
        deduped.append(image)
    return YupooAlbumProduct(
        normalize_url(page_url),
        title,
        description,
        [image["src"] for image in deduped][:MAX_IMAGES_PER_ITEM],
        [image.get("alt") or image.get("title") or "" for image in deduped][:MAX_IMAGES_PER_ITEM],
    )


def owner_from_yupoo_page(html_body: str) -> str:
    match = re.search(r'window\.OWNER\s*=\s*[\'"]([^\'"]+)[\'"]', html_body)
    return match.group(1) if match else ""


def yupoo_media_key(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return normalize_url(url)


def is_ignored_yupoo_gallery_image(image: dict) -> bool:
    text = normalize_product_text(" ".join(str(image.get(key, "")) for key in ["src", "alt", "title", "class", "id"]))
    ignored = {"logo", "avatar", "qrcode", "qr code", "icon", "play", "search", "weibo", "placeholder", "loading"}
    return any(normalize_product_text(term) in text for term in ignored)


class SafeHTTPFetcher:
    def __init__(self, allowed_hosts: list[str] | None = None):
        self.allowed_hosts = allowed_hosts or settings.import_allowed_host_list

    def get(self, url: str) -> FetchedPage:
        current_url = validate_source_url(url, self.allowed_hosts)
        last_error: Exception | None = None
        for attempt in range(settings.import_max_retries + 1):
            try:
                with httpx.Client(
                    timeout=settings.import_request_timeout,
                    follow_redirects=False,
                    headers={"User-Agent": settings.import_user_agent},
                    verify=build_verified_ssl_context(),
                ) as client:
                    redirects = 0
                    while True:
                        with client.stream("GET", current_url) as response:
                            if response.status_code in {301, 302, 303, 307, 308}:
                                location = response.headers.get("location")
                                if not location:
                                    raise ApiError(502, "IMPORT_REDIRECT_INVALID", "Redirect sem destino valido.")
                                redirects += 1
                                if redirects > settings.import_image_max_redirects:
                                    raise ApiError(310, "IMPORT_TOO_MANY_REDIRECTS", "Fonte excedeu o limite de redirects.")
                                current_url = validate_source_url(urljoin(current_url, location), self.allowed_hosts)
                                continue
                            content = bytearray()
                            for chunk in response.iter_bytes(READ_CHUNK_SIZE):
                                if not chunk:
                                    continue
                                content.extend(chunk)
                                if len(content) > settings.import_max_response_bytes:
                                    raise ApiError(413, "IMPORT_RESPONSE_TOO_LARGE", "Resposta da fonte excede o limite.")
                            body = bytes(content)
                            break
                validate_source_url(str(response.url), self.allowed_hosts)
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if response.status_code == 404:
                    raise ApiError(404, "IMPORT_SOURCE_NOT_FOUND", "Pasta nao encontrada.")
                if response.status_code == 429:
                    raise ApiError(429, "IMPORT_SOURCE_RATE_LIMITED", "Fonte limitou as requisicoes.")
                if response.status_code >= 500:
                    raise ApiError(502, "IMPORT_SOURCE_ERROR", "Fonte retornou erro temporario.")
                if not content_type.startswith("text/html"):
                    raise ApiError(415, "IMPORT_CONTENT_TYPE", "A fonte nao retornou HTML.")
                return FetchedPage(str(response.url), body.decode(response.encoding or "utf-8", errors="replace"), content_type, response.status_code)
            except ApiError:
                raise
            except httpx.TimeoutException as exc:
                last_error = exc
            except httpx.HTTPError as exc:
                if is_tls_verification_error(exc):
                    raise ApiError(495, "IMPORT_TLS_VERIFICATION_FAILED", TLS_ERROR_MESSAGE) from exc
                last_error = exc
            if attempt < settings.import_max_retries:
                time.sleep(settings.import_request_delay)
        raise ApiError(504, "IMPORT_SOURCE_TIMEOUT", "Tempo limite ao consultar a fonte.") from last_error


def normalize_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in IGNORED_QUERY_KEYS or any(lowered.startswith(prefix) for prefix in IGNORED_QUERY_PREFIXES):
            continue
        query.append((key, value))
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    netloc = normalized_netloc(parsed.hostname, parsed.port) if parsed.hostname else parsed.netloc.lower().rstrip(".")
    normalized = parsed._replace(scheme=parsed.scheme.lower(), netloc=netloc, path=path, params="", query=urlencode(sorted(query)), fragment="")
    return urlunparse(normalized)


def normalize_legacy_yupoo_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    host = normalize_hostname(parsed.hostname or "") if parsed.hostname else ""
    if host not in {"yupoo.com", "www.yupoo.com"}:
        return url
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "photos":
        return url
    catalog = parts[1].casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", catalog):
        raise ApiError(422, "IMPORT_INVALID_LEGACY_YUPOO_URL", "URL antiga do Yupoo possui catalogo invalido.")
    rest = parts[2:]
    if not rest:
        new_path = "/albums"
    elif rest[0] in {"albums", "categories", "collections"} and (len(rest) == 1 or re.fullmatch(r"\d+", rest[1] or "")):
        new_path = "/" + "/".join(rest[:2])
    else:
        raise ApiError(422, "IMPORT_INVALID_LEGACY_YUPOO_URL", "URL antiga do Yupoo nao e suportada.")
    return urlunparse(parsed._replace(scheme="https", netloc=f"{catalog}.x.yupoo.com", path=new_path, params="", fragment=""))


def canonical_yupoo_source_url(url: str) -> str:
    normalized = normalize_url(normalize_legacy_yupoo_url(url))
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/") or "/"
    if host.endswith(".x.yupoo.com") and path == "/":
        return urlunparse(parsed._replace(path="/albums"))
    return normalized


def new_import_scan_state(root_url: str) -> ImportScanState:
    normalized = normalize_url(root_url)
    return ImportScanState([normalized], set(), {normalized}, set())


def import_scan_metadata(state: ImportScanState, *, max_pages: int, max_items: int) -> dict:
    return {
        "pages_read": state.pages_read,
        "last_page_processed": state.last_page_processed,
        "raw_items_found": state.raw_items_found,
        "unique_items_found": state.unique_items_found,
        "duplicates_removed": state.duplicate_items_removed,
        "processed_items": state.processed_items,
        "truncated": state.truncated,
        "pagination_truncated": state.pagination_truncated,
        "limit_reason": state.limit_reason,
        "pending_pages": len(state.pages_to_visit),
        "limits": {"max_pages": max_pages, "max_items": max_items},
    }


def validate_source_url(url: str, allowed_hosts: list[str] | None = None) -> str:
    allowed = allowed_hosts or settings.import_allowed_host_list
    url = normalize_legacy_yupoo_url(url)
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ApiError(422, "IMPORT_INVALID_URL", "Informe uma URL HTTP ou HTTPS valida.")
    validate_url_authority(url, code="IMPORT_INVALID_URL", message="Informe uma URL HTTP ou HTTPS valida.")
    host = normalize_hostname(parsed.hostname)
    if not is_allowed_import_host(host, allowed):
        raise ApiError(422, "IMPORT_HOST_NOT_ALLOWED", "A fonte informada nao esta permitida.")
    for address in resolve_source_hostname(host):
        if is_blocked_source_ip(address):
            raise ApiError(422, "IMPORT_SSRF_BLOCKED", "Enderecos locais ou privados nao sao permitidos.")
    return normalize_url(url)


def is_allowed_import_host(host: str, allowed_hosts: list[str] | None = None, allowed_domains: list[str] | None = None) -> bool:
    exact_hosts = {normalize_hostname(item) for item in (allowed_hosts or settings.import_allowed_host_list)}
    domains = {normalize_hostname(item) for item in (allowed_domains or settings.import_allowed_domain_list)}
    if host in exact_hosts:
        return True
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def is_blocked_source_ip(address: str) -> bool:
    return is_blocked_ip(address)


def resolve_source_hostname(hostname: str) -> list[str]:
    try:
        return resolve_public_hostname(hostname)
    except ApiError as exc:
        raise ApiError(422, "IMPORT_HOST_NOT_RESOLVED", "Nao foi possivel validar o host informado.", exc.details) from exc


def item_dedupe_key_for_import(source_url: str, *, source: str = "folder_preview", source_type: str = "folder") -> str:
    identity = resolve_import_identity(source=source, source_type=source_type, source_url=source_url, normalized_source_url=normalize_url(source_url))
    return identity.dedupe_key


def is_url_inside_import_scope(candidate_url: str, root_folder_url: str) -> bool:
    candidate = urlparse(normalize_url(candidate_url))
    root = urlparse(normalize_url(root_folder_url))
    if candidate.scheme not in {"http", "https"} or candidate.netloc != root.netloc:
        return False
    root_path = root.path.rstrip("/") or "/"
    candidate_path = candidate.path.rstrip("/") or "/"
    if candidate_path == root_path:
        return True
    if root_path != "/" and candidate_path.startswith(f"{root_path}/"):
        return True
    return False


def is_same_yupoo_category_page(candidate_url: str, root_url: str) -> bool:
    candidate = urlparse(normalize_url(candidate_url))
    root = urlparse(normalize_url(root_url))
    return candidate.netloc == root.netloc and candidate.path.rstrip("/") == root.path.rstrip("/")


def page_number_from_url(url: str) -> int | None:
    parsed = urlparse(normalize_url(url))
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in PAGE_QUERY_KEYS:
            try:
                number = int(value)
            except ValueError:
                return None
            return number if number > 0 else None
    return None


def next_category_page_url(page_url: str, root_url: str) -> str | None:
    if not is_same_yupoo_category_page(page_url, root_url):
        return None
    parsed = urlparse(normalize_url(page_url))
    current = page_number_from_url(page_url) or 1
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in PAGE_QUERY_KEYS]
    query.append(("page", str(current + 1)))
    return urlunparse(parsed._replace(query=urlencode(sorted(query))))


def category_page_url(root_url: str, page_number: int) -> str:
    parsed = urlparse(normalize_url(root_url))
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in PAGE_QUERY_KEYS]
    if page_number > 1 or any(key in PAGE_QUERY_KEYS for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        query.append(("page", str(max(1, page_number))))
    return urlunparse(parsed._replace(query=urlencode(sorted(query))))


def queue_discovered_pages(state: ImportScanState, root_url: str, current_page_url: str, discovered_pages: list[str], *, saw_candidates: bool, max_pages: int, auto_increment: bool = False) -> None:
    page_candidates = []
    for page_url in discovered_pages:
        normalized = normalize_url(page_url)
        if is_same_yupoo_category_page(normalized, root_url):
            page_candidates.append(normalized)
    if saw_candidates and auto_increment:
        generated = next_category_page_url(current_page_url, root_url)
        if generated:
            page_candidates.append(generated)
    for page_url in sorted(dict.fromkeys(page_candidates), key=lambda item: page_number_from_url(item) or 1):
        if page_url in state.visited_pages or page_url in state.queued_pages:
            continue
        if len(state.visited_pages) + len(state.pages_to_visit) >= max_pages:
            state.pagination_truncated = True
            if not state.limit_reason:
                state.limit_reason = "max_pages"
            continue
        state.pages_to_visit.append(page_url)
        state.queued_pages.add(page_url)


def unique_scan_candidates(state: ImportScanState, candidates: list[CandidateItem], *, source: str = "folder_preview", source_type: str = "folder") -> list[CandidateItem]:
    unique: list[CandidateItem] = []
    state.raw_items_found += len(candidates)
    for candidate in candidates:
        key = item_dedupe_key_for_import(candidate.source_url, source=source, source_type=source_type)
        if key in state.seen_item_keys:
            state.duplicate_items_removed += 1
            continue
        state.seen_item_keys.add(key)
        state.unique_items_found += 1
        unique.append(candidate)
    return unique


def resolve_brand(db: Session, *, brand_id: int | None = None, brand: str | None = None) -> Brand:
    if brand_id:
        item = db.get(Brand, brand_id)
        if item:
            return item
    if brand:
        normalized = slugify(brand)
        item = db.query(Brand).filter(or_(Brand.slug == normalized, Brand.name.ilike(brand.strip()))).first()
        if item:
            return item
    raise ApiError(422, "IMPORT_BRAND_NOT_FOUND", "A marca informada nao esta cadastrada.")


def folder_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    value = parsed.path.rstrip("/").split("/")[-1] or parsed.hostname or "pasta"
    return value[:220]


def external_id_from_url(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:24]


def parse_page(url: str, html: str) -> tuple[str, list[tuple[str, str]], list[dict]]:
    parser = ImportHTMLParser(url)
    parser.feed(html)
    title = " ".join(parser.title_parts).strip()
    return title, parser.links, parser.images


def normalize_product_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[_\-\/]+", " ", text)
    text = re.sub(r"[^a-zA-Z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def evidence(matched_terms: list[str] | None = None, sources: list[str] | None = None, conflicts: list[str] | None = None, notes: list[str] | None = None) -> dict:
    return {"matched_terms": matched_terms or [], "sources": sources or [], "conflicts": conflicts or [], "notes": notes or []}


def find_terms(normalized_text: str, terms: list[str]) -> list[str]:
    haystack = f" {normalized_text} "
    matches = []
    for term in sorted(terms, key=len, reverse=True):
        normalized_term = normalize_product_text(term)
        if f" {normalized_term} " in haystack and normalized_term not in [normalize_product_text(item) for item in matches]:
            matches.append(term)
    return matches


def classify_category(db: Session, text_by_source: dict[str, str]) -> tuple[str | None, int | None, float, dict, list[str]]:
    combined = normalize_product_text(" ".join(text_by_source.values()))
    scored: list[tuple[str, list[str]]] = []
    for category, terms in CATEGORY_RULES.items():
        matches = find_terms(combined, terms)
        if matches:
            scored.append((category, matches))
    if not scored:
        return None, None, 0.0, evidence(notes=["category_low_confidence"]), ["missing_category"]
    scored.sort(key=lambda item: (len(item[1]), max(len(term) for term in item[1])), reverse=True)
    category, matches = scored[0]
    conflicts = [item[0] for item in scored[1:] if len(item[1]) == len(matches)]
    confidence = min(0.97, 0.58 + 0.13 * len(matches) + 0.06 * int(any(len(term.split()) > 1 for term in matches)))
    warnings = ["ambiguous_category"] if conflicts else []
    if conflicts:
        confidence = min(confidence, 0.68)
    category_row = db.query(Category).filter(or_(Category.slug == slugify(category), Category.name.ilike(category))).first()
    sources = [name for name, value in text_by_source.items() if find_terms(normalize_product_text(value), matches)]
    return category, category_row.id if category_row else None, round(confidence, 2), evidence(matches, sources, conflicts), warnings


def extract_model(text_by_source: dict[str, str], brand_name: str) -> tuple[str | None, float, dict, list[str]]:
    combined_by_priority = [(source, normalize_product_text(value)) for source, value in text_by_source.items()]
    brand_key = normalize_product_text(brand_name)
    model_terms = KNOWN_MODELS.get(brand_key, [])
    if not model_terms and "jordan" in " ".join(value for _, value in combined_by_priority):
        model_terms = KNOWN_MODELS.get("jordan", [])
    matches: list[tuple[str, str]] = []
    for source, normalized in combined_by_priority:
        for model in sorted(model_terms, key=len, reverse=True):
            if f" {normalize_product_text(model)} " in f" {normalized} ":
                matches.append((model, source))
    if not matches:
        return None, 0.0, evidence(notes=["model_not_identified"]), ["missing_model"]
    model, source = matches[0]
    conflicts = sorted({item[0] for item in matches[1:] if normalize_product_text(item[0]) != normalize_product_text(model)})
    confidence = 0.94 if source == "title" else 0.82
    warnings = ["ambiguous_model"] if conflicts else []
    if conflicts:
        confidence = min(confidence, 0.62)
    display = " ".join(word.upper() if word in {"00s", "v2"} else word.capitalize() for word in model.split())
    display = display.replace("00S", "00s")
    return display[:180], round(confidence, 2), evidence([model], [source], conflicts), warnings


def extract_color(text_by_source: dict[str, str]) -> tuple[str | None, str | None, float, dict, list[str]]:
    matches: list[tuple[str, str, str]] = []
    source_priority = {"title": 0, "item_slug": 1, "folder_name": 2, "page_title": 3, "image_alt": 4}
    for source, value in text_by_source.items():
        normalized = normalize_product_text(value)
        for color, terms in COLOR_RULES.items():
            found = find_terms(normalized, terms)
            if found:
                matches.append((color, source, found[0]))
    if not matches:
        return None, None, 0.0, evidence(notes=["color_not_identified"]), ["missing_color"]
    matches.sort(key=lambda item: (source_priority.get(item[1], 99), -len(item[2])))
    color, source, term = matches[0]
    conflicts = sorted({item[0] for item in matches[1:] if item[0] != color})
    confidence = 0.90 if len(term.split()) > 1 else 0.78
    warnings = ["ambiguous_color"] if len(conflicts) > 2 else []
    if warnings:
        confidence = min(confidence, 0.65)
    return color, normalize_product_text(color), round(confidence, 2), evidence([term], [source], conflicts[:3]), warnings


def clean_title(value: str, brand_name: str) -> str:
    normalized_brand = normalize_product_text(brand_name)
    parts = []
    for token in re.split(r"\s+", re.sub(r"[_\-]+", " ", value or "")):
        if not token:
            continue
        token_norm = normalize_product_text(token)
        if token_norm in {normalize_product_text(item) for item in NAME_NOISE_TERMS}:
            continue
        parts.append(token)
    cleaned = re.sub(r"\s+", " ", " ".join(parts)).strip()
    words = cleaned.split()
    deduped = []
    for word in words:
        if deduped and normalize_product_text(word) == normalize_product_text(deduped[-1]) == normalized_brand:
            continue
        deduped.append(word)
    return " ".join(deduped).strip()


def build_suggested_name(title: str, brand_name: str, model: str | None, color: str | None) -> tuple[str | None, dict, list[str]]:
    cleaned = clean_title(title, brand_name)
    if not cleaned:
        pieces = [brand_name, model, color]
        name = " ".join(piece for piece in pieces if piece)
        return (name or None), evidence(notes=["name_built_from_parts"]), ["missing_title"]
    if normalize_product_text(brand_name) not in normalize_product_text(cleaned):
        cleaned = f"{brand_name} {cleaned}".strip()
    if brand_name == "Chrome Hearts" and normalize_product_text(cleaned).startswith("ch "):
        cleaned = f"Chrome Hearts {cleaned[3:]}"
    return cleaned[:300], evidence([cleaned], ["title"], notes=["title_cleaned"]), []


def is_ignored_image(image: dict) -> tuple[bool, str | None]:
    text = normalize_product_text(" ".join(str(image.get(key, "")) for key in ["src", "alt", "title", "class", "id"]))
    for term in IGNORED_IMAGE_TERMS:
        if normalize_product_text(term) in text:
            return True, f"{term}_image_removed"
    try:
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
    except ValueError:
        width = height = 0
    if width and height and width * height < 2500:
        return True, "small_image_removed"
    return False, None


def group_images_for_item(candidate_url: str, title: str, all_images: list[dict], fallback_position: int) -> tuple[list[str], float, dict, list[str]]:
    target_text = normalize_product_text(" ".join([urlparse(candidate_url).path, title, folder_name_from_url(candidate_url)]))
    generic_tokens = {
        "adidas",
        "air",
        "balance",
        "folder",
        "front",
        "image",
        "images",
        "item",
        "jordan",
        "main",
        "new",
        "nike",
        "photo",
        "product",
        "side",
        "sneaker",
    }
    target_tokens = [token for token in target_text.split() if len(token) >= 3 and token not in generic_tokens]
    warnings: list[str] = []
    selected: list[str] = []
    for image in all_images:
        ignored, warning = is_ignored_image(image)
        if ignored:
            if warning not in warnings:
                warnings.append(warning)
            continue
        image_text = normalize_product_text(" ".join(str(image.get(key, "")) for key in ["src", "alt", "title"]))
        score = sum(1 for token in target_tokens if token in image_text)
        if score >= 2 or any(len(token) >= 5 and token in image_text for token in target_tokens):
            selected.append(image["src"])
    if not selected and all_images:
        usable = []
        for image in all_images:
            ignored, warning = is_ignored_image(image)
            if ignored:
                if warning not in warnings:
                    warnings.append(warning)
                continue
            usable.append(image["src"])
        if fallback_position - 1 < len(usable):
            selected = [usable[fallback_position - 1]]
    deduped = []
    for url in selected:
        if url not in deduped:
            deduped.append(url)
        elif "duplicate_image_url" not in warnings:
            warnings.append("duplicate_image_url")
    deduped = deduped[:MAX_IMAGES_PER_ITEM]
    confidence = 0.92 if len(deduped) >= 2 else 0.70 if len(deduped) == 1 else 0.35
    if len(deduped) <= 1:
        warnings.append("single_image" if deduped else "missing_image")
    return deduped, confidence, evidence(notes=[f"{len(deduped)} image(s) linked to item"]), warnings


def calculate_overall_confidence(classification: float, grouping: float, model: float, color: float, title: str, warnings: list[str]) -> float:
    title_score = 1.0 if title else 0.25
    color_score = color if color else 0.75
    value = (
        classification * CONFIDENCE_WEIGHTS["classification"]
        + grouping * CONFIDENCE_WEIGHTS["grouping"]
        + model * CONFIDENCE_WEIGHTS["model"]
        + color_score * CONFIDENCE_WEIGHTS["color"]
        + title_score * CONFIDENCE_WEIGHTS["title"]
    )
    if "ambiguous_category" in warnings or "weak_image_group" in warnings:
        value -= 0.18
    return round(max(0.0, min(1.0, value)), 2)


def candidates_from_page(root_url: str, page_url: str, html: str, page_number: int) -> tuple[list[CandidateItem], dict, list[str]]:
    page_type = detect_yupoo_page_type(page_url, html)
    if page_type == "category_page":
        album_links, page_links, metadata = discover_yupoo_album_links(root_url, page_url, html)
        candidates = [
            CandidateItem(
                item.source_url,
                item.title or folder_name_from_url(item.source_url),
                [item.thumbnail_url] if item.thumbnail_url else [],
                page_number,
                position,
                {
                    "page_type": page_type,
                    "page_title": metadata.get("page_title", ""),
                    "grouped_images": [{"src": item.thumbnail_url, "source_type": "album_thumbnail"}] if item.thumbnail_url else [],
                    "grouping_confidence": 0.55 if item.thumbnail_url else 0.0,
                    "grouping_evidence": evidence(notes=["album card discovered on Yupoo category page"]),
                    "grouping_warnings": ["album_page_not_opened"],
                    "album_discovery": metadata,
                },
            )
            for position, item in enumerate(album_links, start=1)
        ]
        counters = {
            "links_found": metadata["albums_found_before_dedupe"],
            "links_in_scope": metadata["albums_valid"],
            "links_out_of_scope": 0,
            "links_invalid": 0,
            "albums_found_before_dedupe": metadata["albums_found_before_dedupe"],
            "albums_valid": metadata["albums_valid"],
            "albums_duplicates_removed": metadata["albums_duplicates_removed"],
        }
        return candidates, counters, page_links
    if page_type == "album_page":
        try:
            product = extract_yupoo_album_product(page_url, html)
        except ApiError:
            return [], {"links_found": 0, "links_in_scope": 0, "links_out_of_scope": 0, "links_invalid": 1}, []
        return [
            CandidateItem(
                product.source_url,
                product.title,
                product.image_urls,
                page_number,
                1,
                {
                    "page_type": page_type,
                    "page_title": product.title,
                    "image_alts": product.image_alts,
                    "grouped_images": [{"src": url, "source_type": "album_gallery"} for url in product.image_urls],
                    "grouping_confidence": 0.94 if product.image_urls else 0.35,
                    "grouping_evidence": evidence(notes=[f"{len(product.image_urls)} Yupoo gallery image(s) linked to album"]),
                    "grouping_warnings": [] if product.image_urls else ["missing_image"],
                },
            )
        ], {"links_found": 1, "links_in_scope": 1, "links_out_of_scope": 0, "links_invalid": 0}, []
    title, links, images = parse_page(page_url, html)
    counters = {"links_found": len(links), "links_in_scope": 0, "links_out_of_scope": 0, "links_invalid": 0}
    item_links: list[tuple[str, str]] = []
    page_links: list[str] = []
    for href, text in links:
        try:
            if is_url_inside_import_scope(href, root_url):
                counters["links_in_scope"] += 1
                parsed = urlparse(normalize_url(href))
                query_keys = {key for key, _ in parse_qsl(parsed.query)}
                if query_keys & PAGE_QUERY_KEYS or normalize_url(href) == normalize_url(root_url):
                    page_links.append(normalize_url(href))
                else:
                    item_links.append((normalize_url(href), text))
            else:
                counters["links_out_of_scope"] += 1
        except Exception:
            counters["links_invalid"] += 1
    candidates: list[CandidateItem] = []
    scoped_images = [image for image in images if is_url_inside_import_scope(image["src"], root_url) or not urlparse(image["src"]).path.lower().endswith((".css", ".js"))]
    if item_links:
        for position, (href, text) in enumerate(item_links, start=1):
            item_title = text or title or folder_name_from_url(href)
            image_urls, grouping_confidence, grouping_evidence, grouping_warnings = group_images_for_item(href, item_title, scoped_images, position)
            grouped_images = grouped_image_details(image_urls, scoped_images)
            candidates.append(
                CandidateItem(
                    href,
                    item_title,
                    image_urls,
                    page_number,
                    position,
                    {
                        "page_title": title,
                        "image_alts": [image.get("alt", "") for image in scoped_images],
                        "grouped_images": grouped_images,
                        "grouping_confidence": grouping_confidence,
                        "grouping_evidence": grouping_evidence,
                        "grouping_warnings": grouping_warnings,
                    },
                )
            )
    elif scoped_images:
        name = title or folder_name_from_url(root_url)
        usable_images = []
        grouped_images = []
        grouping_warnings = []
        for image in scoped_images:
            ignored, warning = is_ignored_image(image)
            if ignored:
                if warning not in grouping_warnings:
                    grouping_warnings.append(warning)
                continue
            usable_images.append(image["src"])
            grouped_images.append(image)
        usable_images = list(dict.fromkeys(usable_images))[:MAX_IMAGES_PER_ITEM]
        grouped_images = grouped_image_details(usable_images, grouped_images)
        grouping_confidence = 0.82 if len(usable_images) >= 2 else 0.62 if usable_images else 0.35
        if len(usable_images) <= 1:
            grouping_warnings.append("single_image" if usable_images else "missing_image")
        candidates.append(
            CandidateItem(
                page_url,
                name,
                usable_images,
                page_number,
                1,
                {
                    "page_title": title,
                    "image_alts": [image.get("alt", "") for image in scoped_images],
                    "grouped_images": grouped_images,
                    "grouping": "page_images",
                    "grouping_confidence": grouping_confidence,
                    "grouping_evidence": evidence(notes=[f"{len(usable_images)} page image(s) linked to item"]),
                    "grouping_warnings": grouping_warnings,
                },
            )
        )
    return candidates, counters, page_links


def grouped_image_details(image_urls: list[str], all_images: list[dict]) -> list[dict]:
    by_src = {}
    for image in all_images:
        by_src.setdefault(image.get("src"), image)
    details = []
    for source_url in image_urls:
        image = dict(by_src.get(source_url, {"src": source_url}))
        image["src"] = source_url
        image["source_type"] = "scanner"
        details.append(image)
    return details


def preview_import_folder(db: Session, *, brand_id: int | None, brand_name: str | None, source_url: str, user_id: int | None, fetcher: Fetcher | None = None) -> ImportRecord:
    brand = resolve_brand(db, brand_id=brand_id, brand=brand_name)
    normalized_url = validate_source_url(source_url)
    existing = (
        db.query(ImportRecord)
        .filter(ImportRecord.brand_id == brand.id, ImportRecord.normalized_source_url == normalized_url, ImportRecord.status.in_(ACTIVE_IMPORT_STATUSES))
        .first()
    )
    if existing:
        raise ApiError(409, "IMPORT_FOLDER_ALREADY_EXISTS", "Ja existe uma importacao ativa ou pronta para esta marca e pasta.")
    fetcher = fetcher or SafeHTTPFetcher()
    record = ImportRecord(
        source="folder_preview",
        external_reference=external_id_from_url(normalized_url),
        status="scanning",
        created_by_id=user_id,
        brand_id=brand.id,
        source_url=source_url,
        normalized_source_url=normalized_url,
        source_type="folder",
        folder_name=folder_name_from_url(normalized_url),
        started_at=utc_now(),
        import_metadata={"scope": {"root_url": normalized_url}, "counters": {}},
    )
    db.add(record)
    db.flush()
    max_pages = settings.import_max_pages
    max_items = settings.import_max_items
    scan_state = new_import_scan_state(normalized_url)
    page_errors: list[dict] = []
    counters = {"links_found": 0, "links_in_scope": 0, "links_out_of_scope": 0, "links_invalid": 0, "images_found": 0}
    seen_items: set[str] = set()
    start = time.monotonic()
    try:
        while scan_state.pages_to_visit and len(scan_state.visited_pages) < max_pages and record.items_found < max_items:
            page_url = scan_state.pages_to_visit.pop(0)
            if page_url in scan_state.visited_pages:
                continue
            scan_state.visited_pages.add(page_url)
            scan_state.pages_read = len(scan_state.visited_pages)
            scan_state.last_page_processed = page_url
            record.current_page = scan_state.pages_read
            try:
                page = fetcher.get(page_url)
                candidates, page_counters, discovered_pages = candidates_from_page(normalized_url, page.url, page.body, record.current_page)
                unique_candidates = unique_scan_candidates(scan_state, candidates, source=record.source, source_type="yupoo" if candidates and candidates[0].raw_metadata.get("page_type") == "category_page" else record.source_type)
                for key, value in page_counters.items():
                    counters[key] = counters.get(key, 0) + value
                is_yupoo_category = bool(candidates) and candidates[0].raw_metadata.get("page_type") == "category_page"
                queue_discovered_pages(scan_state, normalized_url, page.url, discovered_pages, saw_candidates=bool(candidates), max_pages=max_pages, auto_increment=is_yupoo_category)
                for candidate in unique_candidates:
                    if record.items_found >= max_items:
                        scan_state.truncated = True
                        scan_state.limit_reason = scan_state.limit_reason or "max_items"
                        break
                    normalized_item_url = normalize_url(candidate.source_url)
                    external_id = external_id_from_url(normalized_item_url)
                    text_by_source = {
                        "title": candidate.title,
                        "folder_name": record.folder_name or "",
                        "item_slug": folder_name_from_url(normalized_item_url),
                        "page_title": str(candidate.raw_metadata.get("page_title", "")),
                        "image_alt": " ".join(candidate.raw_metadata.get("image_alts", [])),
                    }
                    category, category_id, classification_confidence, classification_evidence, classification_warnings = classify_category(db, text_by_source)
                    model, model_confidence, model_evidence, model_warnings = extract_model(text_by_source, brand.name)
                    color, color_normalized, color_confidence, color_evidence, color_warnings = extract_color(text_by_source)
                    suggested_name, name_evidence, name_warnings = build_suggested_name(candidate.title, brand.name, model, color)
                    grouping_confidence = round(float(candidate.raw_metadata.get("grouping_confidence", 0.35)), 2)
                    grouping_evidence = candidate.raw_metadata.get("grouping_evidence") or evidence(notes=["grouping_not_available"])
                    warnings = list(
                        dict.fromkeys(
                            classification_warnings
                            + model_warnings
                            + color_warnings
                            + name_warnings
                            + candidate.raw_metadata.get("grouping_warnings", [])
                        )
                    )
                    overall_confidence = calculate_overall_confidence(
                        classification_confidence,
                        grouping_confidence,
                        model_confidence,
                        color_confidence,
                        candidate.title,
                        warnings,
                    )
                    status = "pending" if overall_confidence >= 0.85 and classification_confidence >= 0.75 and grouping_confidence >= 0.70 else "needs_review"
                    duplicate_reason = None
                    identity = resolve_import_identity(
                        source=record.source,
                        source_type=record.source_type,
                        external_id=external_id,
                        source_url=candidate.source_url,
                        normalized_source_url=normalized_item_url,
                    )
                    identity_check = find_existing_import_item(db, identity, current_record_id=record.id)
                    warnings = list(dict.fromkeys(warnings + identity_check.warnings))
                    dedupe_key = item_dedupe_key_for_import(normalized_item_url, source=record.source, source_type="yupoo" if candidate.raw_metadata.get("page_type") == "category_page" else record.source_type)
                    if dedupe_key in seen_items:
                        status = "duplicate"
                        duplicate_reason = "same_source_url_in_import"
                    elif identity_check.status in {"exact_duplicate", "same_source_existing"}:
                        status = "duplicate"
                        duplicate_reason = identity_check.status
                    elif identity_check.status in {"conflicting_identity", "manual_review"}:
                        status = "needs_review"
                        duplicate_reason = identity_check.status
                        warnings = list(dict.fromkeys(warnings + [identity_check.status]))
                    seen_items.add(dedupe_key)
                    item = ImportItem(
                        import_record_id=record.id,
                        external_id=external_id,
                        source_url=candidate.source_url,
                        normalized_source_url=normalized_item_url,
                        source_title=candidate.title,
                        suggested_name=suggested_name,
                        brand_id=brand.id,
                        suggested_category=category,
                        suggested_category_id=category_id,
                        suggested_model=model,
                        suggested_color=color,
                        suggested_color_normalized=color_normalized,
                        confidence=overall_confidence,
                        classification_confidence=classification_confidence,
                        model_confidence=model_confidence,
                        color_confidence=color_confidence,
                        grouping_confidence=grouping_confidence,
                        overall_confidence=overall_confidence,
                        status=status if status in ITEM_STATUSES else "needs_review",
                        image_urls=candidate.image_urls,
                        cover_image_url=candidate.image_urls[0] if candidate.image_urls else None,
                        image_count=len(candidate.image_urls),
                        page_number=candidate.page_number,
                        position=candidate.position,
                        duplicate_reason=duplicate_reason,
                        warnings=warnings,
                        classification_evidence=classification_evidence,
                        model_evidence=model_evidence,
                        color_evidence=color_evidence,
                        grouping_evidence=grouping_evidence,
                        raw_metadata={**candidate.raw_metadata, "name_evidence": name_evidence},
                    )
                    from app.services.import_review import create_import_images_for_item, sync_import_item_image_summary

                    create_import_images_for_item(item, candidate.raw_metadata.get("grouped_images", []))
                    db.add(item)
                    db.flush()
                    if user_id and item.images:
                        from app.services.import_image_ingestion import AUTO_IMAGE_DOWNLOAD_CONCURRENCY, ingest_import_item_images

                        user = db.get(AdminUser, user_id)
                        if user:
                            image_result = ingest_import_item_images(db, item=item, user=user)
                            sync_import_item_image_summary(item)
                            item.raw_metadata = {
                                **(item.raw_metadata or {}),
                                "image_ingestion": {
                                    **image_result,
                                    "concurrency": AUTO_IMAGE_DOWNLOAD_CONCURRENCY,
                                },
                            }
                    record.items_found += 1
                    if item.status == "duplicate":
                        record.duplicate_items += 1
                    elif item.status == "pending":
                        record.items_pending += 1
                    else:
                        record.items_pending += 1
                    scan_state.processed_items += 1
                counters["images_found"] += len(parse_page(page.url, page.body)[2])
                time.sleep(settings.import_request_delay)
            except ApiError as exc:
                record.error_count += 1
                page_errors.append({"page": page_url, "code": exc.code, "message": exc.message})
                logger.warning("import_preview_page_failed", extra={"import_id": record.id, "brand_id": brand.id, "host": urlparse(normalized_url).hostname, "current_page": record.current_page, "status": record.status, "error_type": exc.code})
                if not record.items_found:
                    raise
        if scan_state.pages_to_visit and len(scan_state.visited_pages) >= max_pages:
            scan_state.pagination_truncated = True
            scan_state.limit_reason = scan_state.limit_reason or "max_pages"
        if record.items_found >= max_items and (scan_state.unique_items_found > scan_state.processed_items or scan_state.pages_to_visit):
            scan_state.truncated = True
            scan_state.limit_reason = scan_state.limit_reason or "max_items"
        record.total_pages = len(scan_state.visited_pages)
        record.status = FINAL_PREVIEW_STATUS if record.items_found or not page_errors else "failed"
        if not record.items_found:
            record.status = FINAL_PREVIEW_STATUS
            record.error_message = "Nenhum item encontrado na pasta informada."
        db.flush()
        from app.services.import_review import refresh_import_record_counters_from_db

        refresh_import_record_counters_from_db(db, record)
        record.import_metadata = {
            "scope": {"root_url": normalized_url, "host": urlparse(normalized_url).hostname},
            "counters": counters,
            "scan": import_scan_metadata(scan_state, max_pages=max_pages, max_items=max_items),
            "limits": {"max_pages": max_pages, "max_items": max_items},
            "page_errors": page_errors,
            "duration_seconds": round(time.monotonic() - start, 3),
        }
    except ApiError as exc:
        record.status = "failed"
        record.error_message = exc.message
        record.import_metadata = {"scope": {"root_url": normalized_url}, "counters": counters, "page_errors": page_errors, "duration_seconds": round(time.monotonic() - start, 3)}
    finally:
        record.finished_at = utc_now()
        logger.info("import_preview_finished", extra={"import_id": record.id, "brand_id": brand.id, "host": urlparse(normalized_url).hostname, "current_page": record.current_page, "items_found": record.items_found, "duration": record.import_metadata.get("duration_seconds") if record.import_metadata else None, "status": record.status})
    return record
