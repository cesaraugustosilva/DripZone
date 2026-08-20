from io import BytesIO
import socket

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.exceptions import ApiError
from app.services.import_image_ingestion import download_to_temp, validate_downloaded_image, validate_image_url, validate_yupoo_media_url
from app.services.imports import canonical_yupoo_source_url, discover_yupoo_album_links, extract_yupoo_album_product, parse_yupoo_page, validate_source_url


def tiny_image_bytes(fmt="PNG") -> bytes:
    data = BytesIO()
    Image.new("RGB", (10, 10), "white").save(data, format=fmt)
    return data.getvalue()


def album_html_with_attrs(album_id, attrs_by_image, *, title=None, description=None, body_text=""):
    page_title = title or f"Album {album_id}"
    meta = f'<meta name="description" content="{description}">' if description else ""
    body = [f"<html><head><title>{page_title}</title>{meta}</head><body>{body_text}"]
    for index, attrs in enumerate(attrs_by_image, start=1):
        attr_text = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        body.append(f'<img data-type="photo" data-photoindex="{index}" {attr_text}>')
    body.append("</body></html>")
    return "".join(body)


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
        "data:image/png;base64,aaa",
        "https://user:pass@photo.yupoo.com/a.jpg",
        "https://photo.yupoo.com:22/a.jpg",
    ],
)
def test_image_url_blocks_unsupported_schemes_userinfo_and_ports(url, monkeypatch):
    monkeypatch.setattr("app.services.import_image_ingestion.socket.getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))])

    with pytest.raises(ApiError):
        validate_image_url(url)


def test_yupoo_image_redirect_revalidates_destination_before_request(tmp_path, monkeypatch):
    location = "https://127.0.0.1/private.jpg"
    seen = []
    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])

    def handler(request):
        seen.append(str(request.url))
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


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_downloaded_image_allows_only_real_supported_formats(fmt, mime, tmp_path):
    path = tmp_path / f"image.{fmt.lower()}"
    path.write_bytes(tiny_image_bytes(fmt))

    assert validate_downloaded_image(path, mime)[:3] == (mime, 10, 10)


@pytest.mark.parametrize(
    "legacy,canonical",
    [
        ("https://www.yupoo.com/photos/seller/albums/123?uid=1", "https://seller.x.yupoo.com/albums/123?uid=1"),
        ("https://yupoo.com/photos/seller/categories/456", "https://seller.x.yupoo.com/categories/456"),
        ("https://yupoo.com/photos/seller/collections/789", "https://seller.x.yupoo.com/collections/789"),
    ],
)
def test_legacy_yupoo_urls_are_normalized_and_then_validated(legacy, canonical, monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", lambda hostname: ["93.184.216.34"])

    assert validate_source_url(legacy) == canonical
    assert canonical_yupoo_source_url(legacy) == canonical


def test_catalog_root_is_canonicalized_to_albums(monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", lambda hostname: ["93.184.216.34"])

    assert canonical_yupoo_source_url("https://seller.x.yupoo.com/") == "https://seller.x.yupoo.com/albums"


def test_pagination_fallback_from_max_control_and_absurd_max_is_limited():
    root = "https://seller.x.yupoo.com/categories/1?page=1"
    html = """
    <html><body>
      <a class="album__main" title="A" href="/albums/1"></a>
      <input name="page" max="999999" value="1">
    </body></html>
    """

    _, next_pages, _ = discover_yupoo_album_links(root, root, html)

    assert "https://seller.x.yupoo.com/categories/1?page=2" in next_pages
    assert len(next_pages) == 499


def test_invalid_pagination_max_is_ignored():
    root = "https://seller.x.yupoo.com/categories/1?page=1"
    html = '<html><body><input name="page" max="nope"></body></html>'

    _, _, _, _, pagination = parse_yupoo_page(root, html)

    assert pagination == []


def test_collection_pagination_stays_available():
    root = "https://seller.x.yupoo.com/collections/55?page=1"
    html = '<html><body><a class="album__main" title="Drop A" href="/albums/100"><img class="album__img" src="//photo.yupoo.com/thumb/100/small.jpg"></a><a class="pagination__button" href="/collections/55?page=2">next</a></body></html>'

    links, next_pages, _ = discover_yupoo_album_links(root, root, html)

    assert links[0].source_url == "https://seller.x.yupoo.com/albums/100"
    assert next_pages == ["https://seller.x.yupoo.com/collections/55?page=2"]


def test_image_source_priority_and_quality_preference():
    html = album_html_with_attrs(
        "100",
        [
            {
                "data-origin-src": "https://photo.yupoo.com/a/original.jpg",
                "data-original": "https://photo.yupoo.com/a/medium.jpg",
                "data-src": "https://photo.yupoo.com/a/small.jpg",
                "src": "https://photo.yupoo.com/a/thumb.jpg",
            },
            {
                "data-original": "https://photo.yupoo.com/b/small.jpg",
                "src": "https://photo.yupoo.com/b/thumb.jpg",
            },
            {"data-src": "https://photo.yupoo.com/c/square.webp"},
            {"src": "https://photo.yupoo.com/d/thumb.jpg"},
        ],
    )

    product = extract_yupoo_album_product("https://seller.x.yupoo.com/albums/100", html)

    assert product.image_urls == [
        "https://photo.yupoo.com/a/original.jpg",
        "https://photo.yupoo.com/b/medium.jpg",
        "https://photo.yupoo.com/c/medium.webp",
        "https://photo.yupoo.com/d/medium.jpg",
    ]
