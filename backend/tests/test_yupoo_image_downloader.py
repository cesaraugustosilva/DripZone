from io import BytesIO
from pathlib import Path
import socket

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.exceptions import ApiError
from app.scripts.download_yupoo_images import ConsoleProgress, print_final_summary
from app.services.import_image_ingestion import download_to_temp, validate_downloaded_image, validate_image_url, validate_yupoo_media_url
from app.services.yupoo_image_downloader import RawDownloadOptions, RawDownloadResult, YupooRawImageDownloader, classify_album_title, extract_album_gallery, is_non_product_album
from app.services.imports import FetchedPage


ROOT = "https://rockets-reps.x.yupoo.com/categories/4621053?page=1"


@pytest.fixture(autouse=True)
def allow_test_hosts(monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", lambda hostname: ["93.184.216.34"])


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def get(self, url):
        self.requests.append(url)
        if url not in self.pages:
            raise ApiError(404, "NOT_FOUND", "missing")
        return FetchedPage(url=url, body=self.pages[url], content_type="text/html", status_code=200)


def category_html(albums, links=()):
    body = ["<html><body>"]
    for album_id, query in albums:
        suffix = f"?{query}" if query else ""
        body.append(f'<a class="album__main" title="Album {album_id}" href="/albums/{album_id}{suffix}"><img class="album__img" src="//photo.yupoo.com/thumb/{album_id}/small.jpg"></a>')
    for link in links:
        body.append(f'<a class="pagination__number" href="{link}">page</a>')
    body.append("</body></html>")
    return "".join(body)


def album_html(album_id, images):
    body = [f"<html><head><title>Album {album_id}</title></head><body>"]
    for index, image in enumerate(images, start=1):
        body.append(f'<img data-type="photo" data-photoindex="{index}" src="{image}" alt="photo {index}">')
    body.append('<img src="//photo.yupoo.com/logo/logo.jpg" alt="logo">')
    body.append("</body></html>")
    return "".join(body)


def category_html_with_titles(albums, links=()):
    body = ["<html><body>"]
    for album_id, title in albums:
        body.append(f'<a class="album__main" title="{title}" href="/albums/{album_id}"><img class="album__img" src="//photo.yupoo.com/thumb/{album_id}/small.jpg"></a>')
    for link in links:
        body.append(f'<a class="pagination__number" href="{link}">page</a>')
    body.append("</body></html>")
    return "".join(body)


def fake_image_downloader_factory(tmp_path, duplicate_sha=False, fail_url=None, html_url=None):
    calls = []

    def download(url, images_dir, album_url):
        calls.append(url)
        if url == fail_url:
            raise ApiError(502, "IMAGE_FAILED", "failed image")
        if url == html_url:
            raise ApiError(415, "IMPORT_IMAGE_INVALID_CONTENT_TYPE", "html rejected")
        temp = images_dir / f"tmp-{len(calls)}.part"
        color = "red" if duplicate_sha else ("red" if len(calls) == 1 else "blue")
        Image.new("RGB", (32, 32), color).save(temp, format="JPEG")
        import hashlib

        digest = hashlib.sha256(temp.read_bytes()).hexdigest()
        return temp, digest, "image/jpeg", 32, 32, temp.stat().st_size

    download.calls = calls
    return download


def failing_image_downloader(error_type):
    calls = []

    def download(url, images_dir, album_url):
        calls.append(url)
        raise ApiError(422, error_type, "failed")

    download.calls = calls
    return download


def tiny_image_bytes(fmt="PNG") -> bytes:
    data = BytesIO()
    Image.new("RGB", (10, 10), "white").save(data, format=fmt)
    return data.getvalue()


def seed_resume_run(tmp_path, *, manifest_items=None, errors=None, albums=None):
    run = tmp_path / "deateath-albums-old"
    images = run / "images"
    images.mkdir(parents=True)
    if manifest_items is None:
        manifest_items = [
            {
                "file": "images/060319.jpg",
                "sha256": "existing-sha",
                "mime": "image/jpeg",
                "width": 32,
                "height": 32,
                "source_url": "https://photo.yupoo.com/a/existing.jpg",
                "album_url": "https://deateath.x.yupoo.com/albums/100",
                "album_id": "100",
                "album_title": "Album 100",
                "position": 1,
                "origins": [],
            }
        ]
    if albums is None:
        albums = [{"album_id": "100", "album_url": "https://deateath.x.yupoo.com/albums/100", "title": "Album 100", "image_files": ["images/060319.jpg"]}]
    if errors is None:
        errors = []
    Image.new("RGB", (32, 32), "red").save(run / "images" / "060319.jpg", format="JPEG")
    import json

    (run / "manifest.json").write_text(json.dumps(manifest_items), encoding="utf-8")
    (run / "albums.json").write_text(json.dumps(albums), encoding="utf-8")
    (run / "errors.json").write_text(json.dumps(errors), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"dry_run": False, "stats": {"pages_read": 84}}), encoding="utf-8")
    return run


def pages_for_two_albums():
    return {
        ROOT: category_html([("100", "uid=1"), ("100", "uid=2"), ("101", "")], links=["/categories/4621053?page=2"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=2": category_html([("102", "")]),
        "https://rockets-reps.x.yupoo.com/albums/100?uid=1": album_html("100", ["https://photo.yupoo.com/a/1.jpg", "https://photo.yupoo.com/a/2.jpg"]),
        "https://rockets-reps.x.yupoo.com/albums/101": album_html("101", ["https://photo.yupoo.com/b/1.jpg"]),
        "https://rockets-reps.x.yupoo.com/albums/102": album_html("102", ["https://photo.yupoo.com/c/1.jpg"]),
    }


def test_dry_run_pagination_album_dedupe_and_gallery_extraction(tmp_path):
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=fake_image_downloader_factory(tmp_path))

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=2, max_albums=2, dry_run=True))

    assert result.stats["albums_found"] == 2
    assert result.stats["images_found"] == 3
    assert result.stats["images_downloaded"] == 0
    assert [album["album_id"] for album in result.albums] == ["100", "101"]


def test_real_run_uses_global_sequence_and_dedupes_by_sha(tmp_path):
    image_downloader = fake_image_downloader_factory(tmp_path, duplicate_sha=True)
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=image_downloader)

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=2))

    assert result.stats["images_downloaded"] == 1
    assert result.stats["exact_duplicates"] == 2
    assert result.manifest[0]["file"] == "images/000001.jpg"
    assert len(result.manifest[0]["origins"]) == 3
    assert (result.run_dir / "manifest.json").is_file()
    assert (result.run_dir / "albums.json").is_file()
    assert (result.run_dir / "errors.json").is_file()


def test_resume_reuses_existing_album_files_without_redownload(tmp_path):
    image_downloader = fake_image_downloader_factory(tmp_path)
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=image_downloader)
    first = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1))
    second_downloader = fake_image_downloader_factory(tmp_path)

    second = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=second_downloader).run(
        RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1, resume=True, run_dir=first.run_dir)
    )

    assert len(second_downloader.calls) == 0
    assert second.stats["images_downloaded"] == 0
    assert second.stats["reused"] == len(first.albums[0]["image_files"])


def test_partial_failure_records_error_and_keeps_other_images(tmp_path):
    failing_url = "https://photo.yupoo.com/a/1.jpg"
    image_downloader = fake_image_downloader_factory(tmp_path, fail_url=failing_url)
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=image_downloader)

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1))

    assert result.stats["errors"] == 1
    assert result.stats["images_downloaded"] == 1
    assert result.errors[0]["image_url"] == failing_url


def test_html_image_response_is_rejected(tmp_path):
    html_url = "https://photo.yupoo.com/a/1.jpg"
    image_downloader = fake_image_downloader_factory(tmp_path, html_url=html_url)
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=image_downloader)

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1))

    assert result.errors[0]["error_type"] == "IMPORT_IMAGE_INVALID_CONTENT_TYPE"
    assert not list((result.run_dir / "images").glob("*.html"))


def test_ssrf_validation_is_preserved(tmp_path):
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher({}), image_downloader=fake_image_downloader_factory(tmp_path))

    with pytest.raises(ApiError):
        downloader.run(RawDownloadOptions(url="http://127.0.0.1/categories/1", output=tmp_path, dry_run=True))


def test_extract_album_gallery_ignores_global_images():
    title, images = extract_album_gallery("https://rockets-reps.x.yupoo.com/albums/100", album_html("100", ["https://photo.yupoo.com/a/1.jpg", "https://photo.yupoo.com/a/qrcode.jpg"]))

    assert title == "100"
    assert images == ["https://photo.yupoo.com/a/1.jpg"]


def test_non_product_album_titles_are_ignored():
    assert is_non_product_album("🔥BRAND")
    assert is_non_product_album("WhatsApp：+852 5736 3298")
    assert is_non_product_album("NEW YUPOO")


def test_product_album_titles_are_preserved():
    assert classify_album_title("¥468 A⭐R J⭐R⭐AN JACKET 22081113001") == "product_candidate"
    assert not is_non_product_album("¥468 A⭐R J⭐R⭐AN JACKET 22081113001")


def test_short_legitimate_title_is_not_discarded():
    assert classify_album_title("AJ4") == "uncertain"
    assert not is_non_product_album("AJ4")


def test_uncertain_album_is_preserved():
    assert classify_album_title("RA⭐⭐H LA⭐RE⭐") == "uncertain"
    assert not is_non_product_album("RA⭐⭐H LA⭐RE⭐")

def test_progress_events_are_emitted_during_download(tmp_path):
    events = []

    def progress(event, **data):
        events.append((event, data))

    downloader = YupooRawImageDownloader(
        fetcher=FakeFetcher(pages_for_two_albums()),
        image_downloader=fake_image_downloader_factory(tmp_path),
        progress=progress,
    )

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1))
    names = [event for event, _ in events]

    assert result.stats["images_downloaded"] == 2
    assert "start" in names
    assert "page_start" in names
    assert "album" in names
    assert "download_plan" in names
    assert "image_download_start" in names
    assert "image_stored" in names
    assert "complete" in names


def test_dns_failure_once_then_succeeds(monkeypatch):
    attempts = []

    def fake_getaddrinfo(hostname, *args, **kwargs):
        attempts.append(hostname)
        if len(attempts) == 1:
            raise socket.gaierror("temporary")
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("app.services.import_image_ingestion.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("app.services.import_image_ingestion.time.sleep", lambda delay: None)

    assert validate_yupoo_media_url("https://photo.yupoo.com/a/1.jpg") == "https://photo.yupoo.com/a/1.jpg"
    assert len(attempts) == 2


def test_dns_failure_persistent_is_blocked_host(monkeypatch):
    monkeypatch.setattr("app.services.import_image_ingestion.socket.getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror("down")))
    monkeypatch.setattr("app.services.import_image_ingestion.time.sleep", lambda delay: None)

    with pytest.raises(ApiError) as exc:
        validate_yupoo_media_url("https://photo.yupoo.com/a/1.jpg")

    assert exc.value.code == "IMPORT_IMAGE_BLOCKED_HOST"


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/a.jpg",
        "https://127.0.0.1/a.jpg",
        "https://[::1]/a.jpg",
        "https://10.0.0.1/a.jpg",
        "https://172.16.0.1/a.jpg",
        "https://192.168.0.1/a.jpg",
        "https://169.254.169.254/a.jpg",
        "https://[fe80::1]/a.jpg",
        "https://[fc00::1]/a.jpg",
        "https://[::ffff:127.0.0.1]/a.jpg",
        "https://2130706433/a.jpg",
        "https://0x7f000001/a.jpg",
        "https://017700000001/a.jpg",
    ],
)
def test_private_and_loopback_ips_stay_blocked(url):
    with pytest.raises(ApiError) as exc:
        validate_image_url(url)

    assert exc.value.code == "IMPORT_IMAGE_BLOCKED_IP"


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/a.jpg",
        "ftp://photo.yupoo.com/a.jpg",
        "gopher://photo.yupoo.com/a.jpg",
        "data:image/png;base64,aaa",
        "javascript:alert(1)",
        "https://user:pass@photo.yupoo.com/a.jpg",
        "https://photo.yupoo.com:22/a.jpg",
        "https://photo.yupoo.com:3000/a.jpg",
    ],
)
def test_image_url_blocks_unsupported_schemes_userinfo_and_ports(url, monkeypatch):
    monkeypatch.setattr("app.services.import_image_ingestion.socket.getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))])

    with pytest.raises(ApiError):
        validate_image_url(url)


def test_image_url_blocks_host_if_any_dns_answer_is_private(monkeypatch):
    monkeypatch.setattr(
        "app.services.import_image_ingestion.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
        ],
    )

    with pytest.raises(ApiError) as exc:
        validate_image_url("https://photo.yupoo.com/a/1.jpg")

    assert exc.value.code == "IMPORT_IMAGE_BLOCKED_IP"


def test_valid_public_host_stays_allowed(monkeypatch):
    monkeypatch.setattr("app.services.import_image_ingestion.socket.getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))])

    assert validate_yupoo_media_url("https://photo.yupoo.com/a/1.jpg") == "https://photo.yupoo.com/a/1.jpg"


@pytest.mark.parametrize(
    "location",
    [
        "https://127.0.0.1/private.jpg",
        "https://private.test/private.jpg",
        "https://evil.example/private.jpg",
        "file:///tmp/private.jpg",
        "https://photo.yupoo.com:22/private.jpg",
    ],
)
def test_yupoo_image_redirect_revalidates_destination_before_request(location, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "app.services.import_image_ingestion.resolve_hostname",
        lambda hostname: ["127.0.0.1"] if hostname == "private.test" else ["93.184.216.34"],
    )

    def handler(request):
        seen.append(str(request.url))
        if str(request.url) != "https://photo.yupoo.com/start.jpg":
            raise AssertionError("redirect target should be blocked before request")
        return httpx.Response(302, headers={"location": location}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(ApiError):
        download_to_temp(client, "https://photo.yupoo.com/start.jpg", tmp_path, yupoo_media_only=True)

    assert seen == ["https://photo.yupoo.com/start.jpg"]


def test_download_blocks_content_length_above_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "import_image_max_bytes", 8)
    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])

    def handler(request):
        return httpx.Response(200, content=b"abcdefghi", headers={"content-type": "image/png", "content-length": "9"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(ApiError) as exc:
        download_to_temp(client, "https://photo.yupoo.com/large.jpg", tmp_path, yupoo_media_only=True)

    assert exc.value.code == "IMPORT_IMAGE_TOO_LARGE"
    assert not list(tmp_path.glob("*.part"))


def test_download_blocks_chunked_body_above_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "import_image_max_bytes", 8)
    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])

    def handler(request):
        return httpx.Response(200, content=b"abcdefghi", headers={"content-type": "image/png"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(ApiError) as exc:
        download_to_temp(client, "https://photo.yupoo.com/chunked.jpg", tmp_path, yupoo_media_only=True)

    assert exc.value.code == "IMPORT_IMAGE_TOO_LARGE"
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_downloaded_image_allows_only_real_supported_formats(fmt, mime, tmp_path):
    path = tmp_path / f"image.{fmt.lower()}"
    path.write_bytes(tiny_image_bytes(fmt))

    assert validate_downloaded_image(path, mime)[:3] == (mime, 10, 10)


@pytest.mark.parametrize(
    "body,header_mime,expected_code",
    [
        (b"not an image", "image/jpeg", "IMPORT_IMAGE_INVALID_SIGNATURE"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/jpeg", "IMPORT_IMAGE_INVALID_SIGNATURE"),
        (None, "image/jpeg", "IMPORT_IMAGE_MIME_MISMATCH"),
    ],
)
def test_downloaded_image_rejects_fake_or_mismatched_content(body, header_mime, expected_code, tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(tiny_image_bytes("PNG") if body is None else body)

    with pytest.raises(ApiError) as exc:
        validate_downloaded_image(path, header_mime)

    assert exc.value.code == expected_code


def test_few_blocked_host_errors_do_not_trigger_circuit_breaker(tmp_path, monkeypatch):
    pages = {
        ROOT: category_html([("100", "")]),
        "https://rockets-reps.x.yupoo.com/albums/100": album_html("100", [f"https://photo.yupoo.com/a/{index}.jpg" for index in range(19)]),
    }
    monkeypatch.setattr("app.services.yupoo_image_downloader.validate_yupoo_media_url", lambda url: (_ for _ in ()).throw(ApiError(422, "IMPORT_IMAGE_BLOCKED_HOST", "blocked")))
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages), image_downloader=failing_image_downloader("IMPORT_IMAGE_BLOCKED_HOST"))

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1))

    assert result.stats["errors"] == 19
    assert result.stats["abort_reason"] is None


def test_systemic_blocked_host_errors_trigger_circuit_breaker(tmp_path, monkeypatch):
    pages = {
        ROOT: category_html([("100", "")]),
        "https://rockets-reps.x.yupoo.com/albums/100": album_html("100", [f"https://photo.yupoo.com/a/{index}.jpg" for index in range(25)]),
    }
    events = []
    monkeypatch.setattr("app.services.yupoo_image_downloader.validate_yupoo_media_url", lambda url: (_ for _ in ()).throw(ApiError(422, "IMPORT_IMAGE_BLOCKED_HOST", "blocked")))
    downloader = YupooRawImageDownloader(
        fetcher=FakeFetcher(pages),
        image_downloader=failing_image_downloader("IMPORT_IMAGE_BLOCKED_HOST"),
        progress=lambda event, **data: events.append(event),
    )

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=1))

    assert result.stats["abort_reason"] == "systemic_image_host_validation_failure"
    assert result.stats["limit_reason"] == "circuit_breaker"
    assert result.stats["truncated"] is True
    assert "host_validation_alert" in events
    assert "aborted" in events


def test_repeated_page_ends_pagination(tmp_path):
    pages = {
        ROOT: category_html([("100", "")], links=["/categories/4621053?page=2"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=2": category_html([("100", "")]),
        "https://rockets-reps.x.yupoo.com/albums/100": album_html("100", ["https://photo.yupoo.com/a/1.jpg"]),
    }
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages), image_downloader=fake_image_downloader_factory(tmp_path))

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=2, max_albums=10, dry_run=True))

    assert result.stats["pagination_end_reached"] is True
    assert result.stats["limit_reason"] == "repeated_page"


def test_no_new_album_ids_ends_pagination(tmp_path):
    pages = {
        ROOT: category_html_with_titles([("100", "BRAND")]),
    }
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages), image_downloader=fake_image_downloader_factory(tmp_path))

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=1, max_albums=10, dry_run=True))

    assert result.stats["pagination_end_reached"] is True
    assert result.stats["limit_reason"] == "no_new_album_ids"


def test_max_album_limit_is_recorded_as_truncated(tmp_path):
    downloader = YupooRawImageDownloader(fetcher=FakeFetcher(pages_for_two_albums()), image_downloader=fake_image_downloader_factory(tmp_path))

    result = downloader.run(RawDownloadOptions(url=ROOT, output=tmp_path, max_pages=2, max_albums=1, dry_run=True))

    assert result.stats["truncated"] is True
    assert result.stats["pagination_end_reached"] is False
    assert result.stats["limit_reason"] == "max_albums"


def test_resume_loads_manifest_and_skips_existing_source_url(tmp_path):
    run = seed_resume_run(
        tmp_path,
        errors=[{"album_url": "https://deateath.x.yupoo.com/albums/100", "image_url": "https://photo.yupoo.com/a/existing.jpg", "error_type": "IMPORT_IMAGE_BLOCKED_HOST"}],
    )
    image_downloader = fake_image_downloader_factory(tmp_path)

    result = YupooRawImageDownloader(fetcher=FakeFetcher({}), image_downloader=image_downloader).run(
        RawDownloadOptions(run_dir=run, resume=True, max_retries=20)
    )

    assert image_downloader.calls == []
    assert result.stats["historical_errors"] == 1
    assert result.stats["unique_pending_retries"] == 0
    assert len(result.manifest) == 1


def test_resume_deduplicates_historical_errors_and_continues_numbering(tmp_path):
    pending = "https://photo.yupoo.com/a/pending.jpg"
    run = seed_resume_run(
        tmp_path,
        errors=[
            {"album_url": "https://deateath.x.yupoo.com/albums/100", "image_url": pending, "error_type": "IMPORT_IMAGE_BLOCKED_HOST"},
            {"album_url": "https://deateath.x.yupoo.com/albums/100", "image_url": pending, "error_type": "IMPORT_IMAGE_BLOCKED_HOST"},
        ],
    )
    image_downloader = fake_image_downloader_factory(tmp_path)

    result = YupooRawImageDownloader(fetcher=FakeFetcher({}), image_downloader=image_downloader).run(
        RawDownloadOptions(run_dir=run, resume=True, max_retries=20)
    )

    assert image_downloader.calls == [pending]
    assert result.stats["historical_errors"] == 2
    assert result.stats["unique_pending_retries"] == 1
    assert result.stats["retried"] == 1
    assert result.stats["recovered"] == 1
    assert result.manifest[-1]["file"] == "images/060320.jpg"
    assert "images/060320.jpg" in result.albums[0]["image_files"]
    assert (run / "retry-summary.json").is_file()


def test_resume_still_failed_is_recorded(tmp_path):
    pending = "https://photo.yupoo.com/a/pending.jpg"
    run = seed_resume_run(
        tmp_path,
        errors=[{"album_url": "https://deateath.x.yupoo.com/albums/100", "image_url": pending, "error_type": "IMPORT_IMAGE_BLOCKED_HOST"}],
    )

    result = YupooRawImageDownloader(fetcher=FakeFetcher({}), image_downloader=failing_image_downloader("ConnectTimeout")).run(
        RawDownloadOptions(run_dir=run, resume=True, max_retries=20)
    )

    assert result.stats["retried"] == 1
    assert result.stats["recovered"] == 0
    assert result.stats["still_failed"] == 1
    assert result.errors[-1]["image_url"] == pending


def test_resume_checkpoint_is_written_on_keyboard_interrupt(tmp_path):
    pending = "https://photo.yupoo.com/a/pending.jpg"
    run = seed_resume_run(
        tmp_path,
        errors=[{"album_url": "https://deateath.x.yupoo.com/albums/100", "image_url": pending, "error_type": "IMPORT_IMAGE_BLOCKED_HOST"}],
    )

    def interrupted(url, images_dir, album_url):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        YupooRawImageDownloader(fetcher=FakeFetcher({}), image_downloader=interrupted).run(
            RawDownloadOptions(run_dir=run, resume=True, max_retries=20)
        )

    import json

    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert summary["stats"]["interrupted"] is True


def test_resume_progress_prints_explicit_start_and_status(capsys):
    progress = ConsoleProgress(verbose=True)
    stats = {
        "historical_errors": 209984,
        "unique_pending_retries": 209964,
        "existing_manifest_files": 60339,
        "physical_files": 60339,
        "images_found": 3,
        "retried": 0,
        "recovered": 0,
        "still_failed": 0,
        "bytes": 0,
    }

    progress("start", url="https://deateath.x.yupoo.com/albums", run_dir="downloads/yupoo/deateath-albums-20260811T061730Z")
    progress("download_plan", stats=stats, albums_total=10000, images_total=3)
    stats.update({"retried": 1, "recovered": 1, "physical_files": 60340, "bytes": 1024 * 1024})
    progress("image_stored", file="images/060340.jpg", stats=stats)
    output = capsys.readouterr().out

    assert "RETOMANDO DOWNLOAD YUPOO" in output
    assert "RETOMADA INICIADA" in output
    assert "Arquivos existentes: 60339" in output
    assert "Pendentes para retry: 209964" in output
    assert "Retries:" in output
    assert "Recuperada: images/060340.jpg" in output


def test_resume_progress_heartbeat_and_final_summary(capsys, tmp_path):
    progress = ConsoleProgress(verbose=True)
    stats = {
        "historical_errors": 10,
        "unique_pending_retries": 3,
        "existing_manifest_files": 5,
        "physical_files": 7,
        "images_found": 3,
        "retried": 2,
        "recovered": 2,
        "still_failed": 0,
        "bytes": 2048,
    }
    progress("download_plan", stats=stats, albums_total=1, images_total=3)
    progress("heartbeat", stats=stats, pending=1)
    result = RawDownloadResult(tmp_path, False, [], [], [], stats)
    print_final_summary(result, 12)
    output = capsys.readouterr().out

    assert "Ainda trabalhando" in output
    assert "RETOMADA CONCLUIDA" in output
    assert "Retries tentados: 2" in output
    assert "Arquivos antes: 5" in output
    assert "Arquivos depois: 7" in output
