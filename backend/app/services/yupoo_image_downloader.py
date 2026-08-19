from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import time
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.config import settings
from app.exceptions import ApiError
from app.services.http_security import build_verified_ssl_context
from app.services.import_image_ingestion import ALLOWED_EXTENSIONS, download_with_retries, validate_downloaded_image, validate_yupoo_media_url
from app.services.imports import (
    FetchedPage,
    Fetcher,
    SafeHTTPFetcher,
    category_page_url,
    clean_yupoo_title,
    discover_yupoo_album_links,
    folder_name_from_url,
    is_ignored_yupoo_gallery_image,
    item_dedupe_key_for_import,
    new_import_scan_state,
    normalize_url,
    parse_yupoo_page,
    queue_discovered_pages,
    validate_source_url,
    yupoo_media_key,
)

MAX_DOWNLOAD_WORKERS = 2
SYSTEMIC_HOST_FAILURE_MIN_ATTEMPTS = 20
SYSTEMIC_HOST_FAILURE_RATIO = 0.8
CHECKPOINT_IMAGE_INTERVAL = 25
PROGRESS_HEARTBEAT_SECONDS = 5
NON_PRODUCT_ALBUM_TERMS = {
    "brand",
    "brands",
    "new yupoo",
    "whatsapp",
    "wechat",
    "telegram",
    "discord",
    "contact",
    "contact us",
    "how to order",
    "how to use",
    "order guide",
    "shipping",
    "qc",
    "yupoo",
    "notice",
    "announcement",
    "price list",
    "agent",
    "seller information",
    "customer reviews",
    "review",
}
NAVIGATION_ALBUM_TERMS = {"hot selling items", "sale", "jewelry"}
CONTACT_ALBUM_TERMS = {"whatsapp", "wechat", "telegram", "discord", "contact", "contact us"}


@dataclass
class RawAlbum:
    album_id: str
    album_url: str
    title: str
    position: int
    page_index: int = 1
    image_urls: list[str] = field(default_factory=list)


@dataclass
class RawDownloadOptions:
    url: str = ""
    output: Path = Path("downloads/yupoo")
    start_page: int = 1
    max_pages: int | None = None
    max_albums: int | None = None
    dry_run: bool = False
    verbose: bool = False
    resume: bool = False
    run_dir: Path | None = None
    max_retries: int | None = None


@dataclass
class RawDownloadResult:
    run_dir: Path
    dry_run: bool
    albums: list[dict]
    manifest: list[dict]
    errors: list[dict]
    stats: dict


class YupooDownloadAborted(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def album_id_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    for index, part in enumerate(parts):
        if part == "albums" and index + 1 < len(parts):
            return parts[index + 1]
    return folder_name_from_url(url)


def normalize_album_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().casefold()
    return re.sub(r"\s+", " ", text)


def classify_album_title(title: str | None) -> str:
    normalized = normalize_album_title(title)
    if not normalized:
        return "uncertain"
    if any(term in normalized for term in CONTACT_ALBUM_TERMS):
        return "contact"
    if normalized in {"brand", "brands", "new yupoo"}:
        return "informational"
    if any(term in normalized for term in NON_PRODUCT_ALBUM_TERMS):
        return "informational"
    if normalized in NAVIGATION_ALBUM_TERMS or any(term in normalized for term in NAVIGATION_ALBUM_TERMS):
        return "navigation"
    if re.search(r"\b(?:[a-z]\d{4,}|r\d{4,}|\d{4,}|(?:¥|usd|\$)\s*\d+|\d+\s*(?:yuan|usd))\b", normalized):
        return "product_candidate"
    if re.search(r"\b(?:shoes?|sneakers?|hoodie|shirt|pants|bag|jacket|tee|shorts|sweater|jersey|cap|hat|headgear)\b", normalized):
        return "product_candidate"
    return "uncertain"


def is_non_product_album(title: str | None) -> bool:
    return classify_album_title(title) in {"navigation", "contact", "informational"}


def run_slug(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    host = (parsed.hostname or "yupoo").split(".")[0]
    category = folder_name_from_url(url)
    safe = re.sub(r"[^a-zA-Z0-9-]+", "-", f"{host}-{category}").strip("-").lower()
    return safe or "yupoo-download"


def ensure_child_path(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve(strict=False)
    candidate_resolved = candidate.resolve(strict=False)
    candidate_resolved.relative_to(root_resolved)
    return candidate_resolved


def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def extract_album_gallery(album_url: str, html_body: str, *, fallback_title: str = "") -> tuple[str, list[str]]:
    page_title, meta, _, gallery_images, _ = parse_yupoo_page(album_url, html_body)
    title = clean_yupoo_title(page_title) or clean_yupoo_title(meta.get("og:title")) or clean_yupoo_title(fallback_title) or folder_name_from_url(album_url)
    ordered = sorted(gallery_images, key=lambda image: int(image.get("position") or 0))
    seen: set[str] = set()
    urls: list[str] = []
    for image in ordered:
        src = image.get("src")
        if not src or is_ignored_yupoo_gallery_image(image):
            continue
        key = yupoo_media_key(src)
        if key in seen:
            continue
        seen.add(key)
        urls.append(src)
    return title, urls


class YupooRawImageDownloader:
    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        image_downloader=None,
        workers: int = MAX_DOWNLOAD_WORKERS,
        progress=None,
    ):
        self.fetcher = fetcher or SafeHTTPFetcher()
        self.image_downloader = image_downloader or self._download_image
        self.workers = max(1, min(MAX_DOWNLOAD_WORKERS, workers))
        self.progress = progress or (lambda event, **data: None)

    def _progress(self, event: str, **data) -> None:
        try:
            self.progress(event, **data)
        except Exception:
            pass

    def run(self, options: RawDownloadOptions) -> RawDownloadResult:
        root_url = validate_source_url(options.url) if options.url else ""
        max_pages = options.max_pages or settings.import_max_pages
        max_albums = options.max_albums or settings.import_max_items
        run_dir = options.run_dir or options.output / f"{run_slug(root_url)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        if not root_url:
            root_url = self._infer_resume_url(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        images_dir = ensure_child_path(run_dir, run_dir / "images")
        images_dir.mkdir(parents=True, exist_ok=True)
        self._progress("start", url=root_url, run_dir=str(run_dir), dry_run=options.dry_run)

        manifest = self._load_manifest(run_dir) if options.resume else []
        errors = self._load_errors(run_dir) if options.resume else []
        files_by_sha = {item["sha256"]: item for item in manifest if item.get("sha256") and (run_dir / item.get("file", "")).is_file()}
        next_index = self._next_index(manifest)

        existing_album_entries = self._load_albums(run_dir) if options.resume else []
        albums = []
        album_entries = list(existing_album_entries)
        downloads = []
        resumed_files = 0
        retry_stats = {"historical_errors": len(errors), "unique_pending_retries": 0, "retried": 0, "recovered": 0, "still_failed": 0, "existing_manifest_files": len(manifest)}
        is_retry_run = bool(options.resume and existing_album_entries and errors)
        if is_retry_run:
            downloads = self._historical_retry_downloads(run_dir, manifest, existing_album_entries, errors, max_retries=options.max_retries)
            retry_stats["unique_pending_retries"] = getattr(self, "unique_pending_retries", len(downloads))
            resumed_files = 0
            albums = [
                RawAlbum(entry.get("album_id", ""), entry.get("album_url", ""), entry.get("title", ""), index + 1, page_index=(index // 120) + 1)
                for index, entry in enumerate(existing_album_entries)
            ]
            self.pages_read = self._load_summary_stats(run_dir).get("pages_read", 0)
            self.album_selection_stats = {}
            self.pagination_stats = {"pagination_end_reached": False, "truncated": False, "limit_reason": "resume_pending_retries", "abort_reason": None}
        else:
            albums = self.collect_albums(root_url, start_page=options.start_page, max_pages=max_pages, max_albums=max_albums, errors=errors)
            album_entries = []
            for album in albums:
                if options.resume and self._album_completed(run_dir, album.album_id):
                    existing = self._album_entry(run_dir, album.album_id)
                    if existing:
                        album_entries.append(existing)
                        resumed_files += len(existing.get("image_files", []))
                        continue
                album_entry = {"album_id": album.album_id, "album_url": album.album_url, "title": album.title, "image_files": []}
                album_entries.append(album_entry)
                for position, image_url in enumerate(album.image_urls, start=1):
                    downloads.append((album, album_entry, position, image_url))

        stats = {
            "pages_read": getattr(self, "pages_read", 0),
            "albums_found": len(albums),
            **getattr(self, "album_selection_stats", {}),
            **getattr(self, "pagination_stats", {}),
            "images_found": len(downloads),
            "images_downloaded": 0,
            "physical_files": len(manifest),
            "bytes": 0,
            "exact_duplicates": 0,
            "errors": 0,
            "reused": resumed_files,
            "abort_reason": None,
            **retry_stats,
        }
        self._progress("download_plan", stats=stats.copy(), albums_total=len(album_entries), images_total=len(downloads))
        if options.dry_run:
            self._write_outputs(run_dir, manifest, album_entries, errors, stats, dry_run=True)
            self._progress("complete", stats=stats.copy(), run_dir=str(run_dir), dry_run=True)
            return RawDownloadResult(run_dir, True, album_entries, manifest, errors, stats)

        aborted = False
        executor = ThreadPoolExecutor(max_workers=self.workers)
        try:
            def download_task(album: RawAlbum, position: int, image_url: str):
                self._progress("image_download_start", album_id=album.album_id, album_title=album.title, position=position, image_url=image_url, stats=stats.copy())
                return self.image_downloader(image_url, images_dir, album.album_url)

            downloads_by_page: dict[int, list[tuple[RawAlbum, dict, int, str]]] = {}
            for item in downloads:
                downloads_by_page.setdefault(item[0].page_index, []).append(item)
            for page_index in sorted(downloads_by_page):
                page_attempts = 0
                page_blocked_host_errors = 0
                blocked_host_urls: list[str] = []
                future_map = {}
                for album, album_entry, position, image_url in downloads_by_page[page_index]:
                    future = executor.submit(download_task, album, position, image_url)
                    future_map[future] = (album, album_entry, position, image_url)
                pending = set(future_map)
                while pending:
                    done, pending = wait(pending, timeout=PROGRESS_HEARTBEAT_SECONDS, return_when=FIRST_COMPLETED)
                    if not done:
                        self._progress("heartbeat", stats=stats.copy(), pending=len(pending))
                        continue
                    for future in done:
                        album, album_entry, position, image_url = future_map[future]
                        page_attempts += 1
                        if is_retry_run:
                            stats["retried"] += 1
                        try:
                            temp_path, sha256, mime, width, height, size_bytes = future.result()
                            if sha256 in files_by_sha:
                                temp_path.unlink(missing_ok=True)
                                record = files_by_sha[sha256]
                                stats["exact_duplicates"] += 1
                                stats["reused"] += 1
                                self._progress("image_duplicate", file=record.get("file"), album_id=album.album_id, album_title=album.title, stats=stats.copy())
                            else:
                                ext = ALLOWED_EXTENSIONS[mime]
                                filename = f"{next_index:06d}.{ext}"
                                next_index += 1
                                final_path = ensure_child_path(run_dir, images_dir / filename)
                                os.replace(temp_path, final_path)
                                record = {
                                    "file": f"images/{filename}",
                                    "sha256": sha256,
                                    "mime": mime,
                                    "width": width,
                                    "height": height,
                                    "source_url": image_url,
                                    "album_url": album.album_url,
                                    "album_id": album.album_id,
                                    "album_title": album.title,
                                    "position": position,
                                    "downloaded_at": utc_iso(),
                                    "origins": [],
                                }
                                manifest.append(record)
                                files_by_sha[sha256] = record
                                stats["images_downloaded"] += 1
                                stats["physical_files"] = len(manifest)
                                stats["bytes"] += size_bytes
                                self._progress("image_stored", file=record.get("file"), album_id=album.album_id, album_title=album.title, size_bytes=size_bytes, stats=stats.copy())
                            origin = {"source_url": image_url, "album_url": album.album_url, "album_id": album.album_id, "album_title": album.title, "position": position}
                            if origin not in record.setdefault("origins", []):
                                record["origins"].append(origin)
                            if record["file"] not in album_entry["image_files"]:
                                album_entry["image_files"].append(record["file"])
                            if is_retry_run:
                                stats["recovered"] += 1
                        except Exception as exc:
                            stats["errors"] += 1
                            if is_retry_run:
                                stats["still_failed"] += 1
                            error = self._error(album.album_url, image_url, exc)
                            errors.append(error)
                            if error["error_type"] == "IMPORT_IMAGE_BLOCKED_HOST":
                                page_blocked_host_errors += 1
                                blocked_host_urls.append(image_url)
                            self._progress("image_error", error=error, album_id=album.album_id, album_title=album.title, stats=stats.copy())
                        if (is_retry_run and stats["retried"] and stats["retried"] % CHECKPOINT_IMAGE_INTERVAL == 0) or (not is_retry_run and stats["images_downloaded"] and stats["images_downloaded"] % CHECKPOINT_IMAGE_INTERVAL == 0):
                            self._write_outputs(run_dir, manifest, album_entries, errors, stats, dry_run=False)
                            self._write_retry_summary(run_dir, stats)
                if self._is_systemic_host_failure(page_attempts, page_blocked_host_errors):
                    self._progress("host_validation_alert", page_index=page_index, attempts=page_attempts, blocked_host_errors=page_blocked_host_errors)
                    if not self._host_validation_probe(blocked_host_urls):
                        stats["abort_reason"] = "systemic_image_host_validation_failure"
                        stats["limit_reason"] = "circuit_breaker"
                        stats["truncated"] = True
                        aborted = True
                        self._progress("aborted", reason=stats["abort_reason"], page_index=page_index, stats=stats.copy(), run_dir=str(run_dir))
                        break
        except KeyboardInterrupt:
            executor.shutdown(wait=False, cancel_futures=True)
            for part_path in images_dir.glob("*.part"):
                part_path.unlink(missing_ok=True)
            stats["interrupted"] = True
            self._write_outputs(run_dir, manifest, album_entries, errors, stats, dry_run=False)
            self._progress("interrupted", stats=stats.copy(), run_dir=str(run_dir))
            raise
        else:
            executor.shutdown(wait=True)

        self._write_outputs(run_dir, manifest, album_entries, errors, stats, dry_run=False)
        self._write_retry_summary(run_dir, stats)
        if not aborted:
            self._progress("complete", stats=stats.copy(), run_dir=str(run_dir), dry_run=False)
        return RawDownloadResult(run_dir, False, album_entries, manifest, errors, stats)

    def _is_systemic_host_failure(self, attempts: int, blocked_host_errors: int) -> bool:
        return attempts >= SYSTEMIC_HOST_FAILURE_MIN_ATTEMPTS and (blocked_host_errors / attempts) >= SYSTEMIC_HOST_FAILURE_RATIO

    def _host_validation_probe(self, image_urls: list[str]) -> bool:
        seen_hosts: set[str] = set()
        for image_url in image_urls[:5]:
            hostname = urlparse(image_url).hostname or ""
            if hostname in seen_hosts:
                continue
            seen_hosts.add(hostname)
            try:
                validate_yupoo_media_url(image_url)
                return True
            except ApiError as exc:
                if exc.code not in {"IMPORT_IMAGE_BLOCKED_HOST", "IMPORT_IMAGE_BLOCKED_IP"}:
                    return True
        return False

    def _historical_retry_downloads(self, run_dir: Path, manifest: list[dict], albums: list[dict], errors: list[dict], *, max_retries: int | None) -> list[tuple[RawAlbum, dict, int, str]]:
        album_entries = {entry.get("album_id"): entry for entry in albums}
        existing_sources: set[str] = set()
        for item in manifest:
            if item.get("source_url"):
                existing_sources.add(item["source_url"])
            for origin in item.get("origins") or []:
                if origin.get("source_url"):
                    existing_sources.add(origin["source_url"])
        pending: list[tuple[RawAlbum, dict, int, str]] = []
        seen: set[tuple[str, str, int]] = set()
        for error in errors:
            image_url = error.get("image_url") or ""
            album_url = error.get("album_url") or ""
            if not image_url or image_url in existing_sources:
                continue
            album_id = album_id_from_url(album_url)
            album_entry = album_entries.get(album_id)
            if not album_entry:
                continue
            position = self._error_position(error)
            key = (image_url, album_url, position)
            if key in seen:
                continue
            seen.add(key)
            album = RawAlbum(album_id, album_url, album_entry.get("title", album_id), position, page_index=self._resume_page_for_album(albums, album_id))
            pending.append((album, album_entry, position, image_url))
        self.unique_pending_retries = len(pending)
        return pending[:max_retries] if max_retries is not None else pending

    def _error_position(self, error: dict) -> int:
        value = error.get("position")
        if isinstance(value, int) and value > 0:
            return value
        return 0

    def _resume_page_for_album(self, albums: list[dict], album_id: str) -> int:
        for index, entry in enumerate(albums):
            if entry.get("album_id") == album_id:
                return (index // 120) + 1
        return 1

    def _infer_resume_url(self, run_dir: Path) -> str:
        albums = self._load_albums(run_dir)
        if not albums:
            raise ApiError(422, "YUPOO_RESUME_RUN_INVALID", "Run nao possui albums.json para inferir origem.")
        parsed = urlparse(albums[0].get("album_url") or "")
        if not parsed.scheme or not parsed.hostname:
            raise ApiError(422, "YUPOO_RESUME_RUN_INVALID", "Run nao possui album_url valido para inferir origem.")
        return f"{parsed.scheme}://{parsed.hostname}/albums"

    def collect_albums(self, root_url: str, *, start_page: int, max_pages: int, max_albums: int, errors: list[dict]) -> list[RawAlbum]:
        start_url = category_page_url(root_url, start_page)
        state = new_import_scan_state(start_url)
        albums: list[RawAlbum] = []
        seen_albums: set[str] = set()
        seen_page_hashes: set[str] = set()
        selection_stats = {"albums_raw": 0, "albums_skipped_non_product": 0, "albums_product_candidates": 0, "albums_uncertain": 0, "albums_skipped_uncertain_non_product": 0}
        pagination_stats = {"pagination_end_reached": False, "truncated": False, "limit_reason": None, "abort_reason": None}
        while state.pages_to_visit and len(state.visited_pages) < max_pages and len(albums) < max_albums:
            page_url = state.pages_to_visit.pop(0)
            if page_url in state.visited_pages:
                continue
            state.visited_pages.add(page_url)
            self._progress("page_start", page_url=page_url, page_index=len(state.visited_pages), max_pages=max_pages)
            page = self.fetcher.get(page_url)
            links, next_pages, _ = discover_yupoo_album_links(root_url, page.url, page.body)
            self._progress("page_albums", page_url=page.url, page_index=len(state.visited_pages), albums_raw=len(links), next_pages=len(next_pages))
            if not links:
                pagination_stats["pagination_end_reached"] = True
                pagination_stats["limit_reason"] = "empty_page"
                break
            page_ids = [album_id_from_url(link.source_url) for link in links]
            page_hash = hashlib.sha1("|".join(page_ids).encode("utf-8")).hexdigest()
            if page_hash in seen_page_hashes:
                pagination_stats["pagination_end_reached"] = True
                pagination_stats["limit_reason"] = "repeated_page"
                break
            seen_page_hashes.add(page_hash)
            new_on_page = 0
            for link in links:
                classification = classify_album_title(link.title)
                selection_stats["albums_raw"] += 1
                if classification == "product_candidate":
                    selection_stats["albums_product_candidates"] += 1
                elif classification == "uncertain":
                    selection_stats["albums_uncertain"] += 1
                if is_non_product_album(link.title):
                    selection_stats["albums_skipped_non_product"] += 1
                    continue
                key = item_dedupe_key_for_import(link.source_url, source="folder_preview", source_type="yupoo")
                if key in seen_albums:
                    continue
                seen_albums.add(key)
                new_on_page += 1
                album = RawAlbum(album_id_from_url(link.source_url), link.source_url, link.title or album_id_from_url(link.source_url), link.position, page_index=len(state.visited_pages))
                try:
                    album_page = self.fetcher.get(album.album_url)
                    title, images = extract_album_gallery(album_page.url, album_page.body, fallback_title=album.title)
                    album.title = title
                    album.image_urls = images
                except Exception as exc:
                    errors.append(self._error(album.album_url, "", exc))
                if classification == "uncertain" and not album.image_urls:
                    selection_stats["albums_skipped_uncertain_non_product"] += 1
                    continue
                albums.append(album)
                self._progress(
                    "album",
                    album_index=len(albums),
                    max_albums=max_albums,
                    album_id=album.album_id,
                    album_url=album.album_url,
                    title=album.title,
                    images_found=len(album.image_urls),
                    classification=classification,
                    page_index=len(state.visited_pages),
                )
                if len(albums) >= max_albums:
                    break
            if new_on_page == 0:
                pagination_stats["pagination_end_reached"] = True
                pagination_stats["limit_reason"] = "no_new_album_ids"
                break
            queue_discovered_pages(state, root_url, page.url, next_pages, saw_candidates=bool(links), max_pages=max_pages, auto_increment=True)
            if settings.import_request_delay > 0:
                time.sleep(settings.import_request_delay)
        if not pagination_stats["pagination_end_reached"]:
            if len(albums) >= max_albums:
                pagination_stats["truncated"] = True
                pagination_stats["limit_reason"] = "max_albums"
            elif len(state.visited_pages) >= max_pages:
                pagination_stats["truncated"] = True
                pagination_stats["limit_reason"] = "max_pages"
        self.pages_read = len(state.visited_pages)
        self.album_selection_stats = selection_stats
        self.pagination_stats = pagination_stats
        return albums

    def _download_image(self, image_url: str, images_dir: Path, album_url: str):
        timeout = httpx.Timeout(connect=settings.import_image_connect_timeout, read=settings.import_image_read_timeout, write=settings.import_image_read_timeout, pool=settings.import_image_connect_timeout)
        with httpx.Client(timeout=timeout, follow_redirects=False, verify=build_verified_ssl_context()) as client:
            temp_path, sha256, header_mime, size_bytes = download_with_retries(client, image_url, images_dir, referer=album_url, yupoo_media_only=True)
        try:
            mime, width, height, _ = validate_downloaded_image(temp_path, header_mime)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return temp_path, sha256, mime, width, height, size_bytes

    def _load_manifest(self, run_dir: Path) -> list[dict]:
        path = run_dir / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []

    def _load_errors(self, run_dir: Path) -> list[dict]:
        path = run_dir / "errors.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []

    def _load_albums(self, run_dir: Path) -> list[dict]:
        path = run_dir / "albums.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []

    def _load_summary_stats(self, run_dir: Path) -> dict:
        path = run_dir / "summary.json"
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("stats", {}) if isinstance(payload, dict) else {}

    def _album_completed(self, run_dir: Path, album_id: str) -> bool:
        entry = self._album_entry(run_dir, album_id)
        return bool(entry and all((run_dir / file).is_file() for file in entry.get("image_files", [])))

    def _album_entry(self, run_dir: Path, album_id: str) -> dict | None:
        path = run_dir / "albums.json"
        if not path.is_file():
            return None
        for item in json.loads(path.read_text(encoding="utf-8")):
            if item.get("album_id") == album_id:
                return item
        return None

    def _next_index(self, manifest: list[dict]) -> int:
        indexes = []
        for item in manifest:
            name = Path(item.get("file", "")).stem
            if name.isdigit():
                indexes.append(int(name))
        return (max(indexes) + 1) if indexes else 1

    def _write_outputs(self, run_dir: Path, manifest: list[dict], albums: list[dict], errors: list[dict], stats: dict, *, dry_run: bool) -> None:
        atomic_write_json(run_dir / "manifest.json", manifest)
        atomic_write_json(run_dir / "albums.json", albums)
        atomic_write_json(run_dir / "errors.json", errors)
        atomic_write_json(run_dir / "summary.json", {"dry_run": dry_run, "stats": stats, "created_at": utc_iso()})

    def _write_retry_summary(self, run_dir: Path, stats: dict) -> None:
        payload = {
            "historical_errors": stats.get("historical_errors", 0),
            "unique_pending_retries": stats.get("unique_pending_retries", 0),
            "retried": stats.get("retried", 0),
            "recovered": stats.get("recovered", 0),
            "still_failed": stats.get("still_failed", 0),
            "existing_manifest_files": stats.get("existing_manifest_files", 0),
            "updated_at": utc_iso(),
        }
        atomic_write_json(run_dir / "retry-summary.json", payload)

    def _error(self, album_url: str, image_url: str, exc: Exception) -> dict:
        return {
            "album_url": album_url,
            "image_url": image_url,
            "error_type": getattr(exc, "code", type(exc).__name__),
            "message": getattr(exc, "message", str(exc)),
            "attempts": settings.import_max_retries + 1,
        }
