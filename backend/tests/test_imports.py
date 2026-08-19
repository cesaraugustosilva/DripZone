import ipaddress
import pytest
import httpx
from io import BytesIO
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.exceptions import ApiError
from app.config import settings
from app.models import Brand, Category, Product
from app.services.imports import FetchedPage, SafeHTTPFetcher, candidates_from_page, is_url_inside_import_scope, preview_import_folder, validate_source_url


FIXTURES = Path(__file__).parent / "fixtures" / "imports"
FIXTURE_MAIN_IMAGE = "https://example.com/folder/images/air-max-95-black-white-main.jpg"
FIXTURE_SIDE_IMAGE = "https://example.com/folder/images/air-max-95-black-white-side.jpg"


def public_dns_or_literal(hostname):
    try:
        ipaddress.ip_address(hostname)
        return [hostname]
    except ValueError:
        return ["93.184.216.34"]


def image_bytes(fmt="JPEG", size=(120, 120)):
    data = BytesIO()
    Image.new("RGB", size, "white").save(data, format=fmt)
    return data.getvalue()


def mock_image_client(monkeypatch, routes):
    original_client = httpx.Client

    def handler(request):
        value = routes.get(str(request.url)) if isinstance(routes, dict) else routes
        if value is None:
            return httpx.Response(404)
        if isinstance(value, httpx.Response):
            return value
        body, mime = value
        return httpx.Response(200, content=body, headers={"content-type": mime})

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            self.client = original_client(transport=httpx.MockTransport(handler))

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr("app.services.import_image_ingestion.httpx.Client", PatchedClient)


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url == "https://example.com/folder?page=2":
            key = url
        else:
            key = url.rstrip("/")
        value = self.pages.get(key)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise ApiError(404, "NOT_FOUND", "Nao encontrado.")
        return FetchedPage(url=url, body=value, content_type="text/html", status_code=200)


def add_brand_and_categories(client, headers):
    brand = client.post("/api/brands", json={"name": "Nike"}, headers=headers).json()
    for name in ["Tenis", "Camisetas", "Moletons", "Jaquetas", "Calcas", "Acessorios"]:
        client.post("/api/categories", json={"name": name}, headers=headers)
    return brand


def folder_html(next_page=False):
    next_link = '<a href="/folder?page=2">2</a>' if next_page else ""
    return f"""
    <html><head><title>Nike Air Max 95</title></head><body>
      <a href="/folder/air-max-95-black">Nike Air Max 95 Black</a>
      <a href="/other-folder/jordan-4">fora</a>
      {next_link}
      <img src="/folder/images/air-max-95-black-1.jpg" alt="Nike Air Max sneaker" />
    </body></html>
    """


def test_url_validation_rejects_invalid_hosts_and_localhost(monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)
    with pytest.raises(ApiError):
        validate_source_url("file:///tmp/import.html")
    with pytest.raises(ApiError):
        validate_source_url("https://localhost/folder")
    with pytest.raises(ApiError):
        validate_source_url("https://127.0.0.1/folder", ["127.0.0.1"])
    with pytest.raises(ApiError):
        validate_source_url("https://not-allowed.test/folder")


def test_url_validation_allows_yupoo_root_and_subdomains(monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)

    assert validate_source_url("https://yupoo.com") == "https://yupoo.com/"
    assert validate_source_url("https://www.yupoo.com") == "https://www.yupoo.com/"
    assert validate_source_url("https://seller.x.yupoo.com/albums/123") == "https://seller.x.yupoo.com/albums/123"
    assert validate_source_url("https://SELLER.X.YUPOO.COM./albums/123") == "https://seller.x.yupoo.com/albums/123"


@pytest.mark.parametrize(
    "url",
    [
        "https://fake-yupoo.com",
        "https://yupoo.com.evil.example",
        "https://evil.example/?next=yupoo.com",
        "http://127.0.0.1",
        "http://localhost",
        "http://192.168.0.10",
        "https://2130706433",
        "https://0x7f000001",
        "https://017700000001",
        "https://user:pass@yupoo.com",
        "https://yupoo.com:22",
        "https://yupoo.com:3000",
        "file:///C:/arquivo",
        "ftp://yupoo.com/folder",
    ],
)
def test_url_validation_blocks_malicious_yupoo_lookalikes_and_local_urls(url, monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)

    with pytest.raises(ApiError):
        validate_source_url(url)


@pytest.mark.parametrize(
    "target_url",
    [
        "http://127.0.0.1/private",
        "http://localhost/private",
        "https://evil.example/folder",
    ],
)
def test_safe_fetcher_validates_redirect_destination(target_url, monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)
    original_client = httpx.Client

    def handler(request):
        if str(request.url) == "https://yupoo.com/start":
            return httpx.Response(302, headers={"location": target_url})
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            self.client = original_client(*args, **kwargs)

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.imports.httpx.Client", PatchedClient)

    with pytest.raises(ApiError):
        SafeHTTPFetcher().get("https://yupoo.com/start")


def test_safe_fetcher_blocks_redirect_before_requesting_target(monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)
    original_client = httpx.Client
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if str(request.url) != "https://yupoo.com/start":
            raise AssertionError("redirect target should be blocked before request")
        return httpx.Response(302, headers={"location": "https://evil.example/folder"}, request=request)

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            self.client = original_client(*args, **kwargs)

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.imports.httpx.Client", PatchedClient)

    with pytest.raises(ApiError):
        SafeHTTPFetcher().get("https://yupoo.com/start")

    assert seen == ["https://yupoo.com/start"]


def test_safe_fetcher_streams_with_response_size_limit(monkeypatch):
    monkeypatch.setattr(settings, "import_max_response_bytes", 8)
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)
    original_client = httpx.Client

    def handler(request):
        return httpx.Response(200, content=b"<html>too large</html>", headers={"content-type": "text/html"}, request=request)

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            self.client = original_client(*args, **kwargs)

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.imports.httpx.Client", PatchedClient)

    with pytest.raises(ApiError) as exc:
        SafeHTTPFetcher().get("https://yupoo.com/start")

    assert exc.value.code == "IMPORT_RESPONSE_TOO_LARGE"


def test_safe_fetcher_stops_redirect_loop(monkeypatch):
    monkeypatch.setattr("app.services.imports.resolve_source_hostname", public_dns_or_literal)
    original_client = httpx.Client

    def handler(request):
        target = "https://yupoo.com/b" if str(request.url) == "https://yupoo.com/a" else "https://yupoo.com/a"
        return httpx.Response(302, headers={"location": target}, request=request)

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            self.client = original_client(*args, **kwargs)

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.imports.httpx.Client", PatchedClient)

    with pytest.raises(ApiError) as exc:
        SafeHTTPFetcher().get("https://yupoo.com/a")

    assert exc.value.code == "IMPORT_TOO_MANY_REDIRECTS"


def test_scope_keeps_scanner_inside_root_folder():
    assert is_url_inside_import_scope("https://example.com/folder/item", "https://example.com/folder")
    assert is_url_inside_import_scope("https://example.com/folder?page=2", "https://example.com/folder")
    assert not is_url_inside_import_scope("https://example.com/other/item", "https://example.com/folder")
    assert not is_url_inside_import_scope("https://other.example.com/folder/item", "https://example.com/folder")


def test_preview_requires_existing_brand(authed):
    client, headers = authed
    response = client.post("/api/imports/preview", json={"brand_id": 999, "source_url": "https://example.com/folder"}, headers=headers)
    assert response.status_code == 422


def test_preview_scans_folder_and_does_not_create_products(authed, monkeypatch):
    client, headers = authed
    brand = add_brand_and_categories(client, headers)
    before = client.get("/api/products").json()["pagination"]["total"]
    fetcher = FakeFetcher({"https://example.com/folder": folder_html()})
    monkeypatch.setattr("app.services.imports.SafeHTTPFetcher", lambda: fetcher)

    response = client.post("/api/imports/preview", json={"brand_id": brand["id"], "source_url": "https://example.com/folder"}, headers=headers)

    assert response.status_code == 201
    import_id = response.json()["id"]
    detail = client.get(f"/api/imports/{import_id}").json()
    items = client.get(f"/api/imports/{import_id}/items").json()["items"]
    after = client.get("/api/products").json()["pagination"]["total"]
    assert before == after
    assert detail["status"] == "preview_ready"
    assert detail["items_found"] == 1
    assert detail["brand_id"] == brand["id"]
    assert items[0]["suggested_category"] == "Tenis"
    assert items[0]["suggested_model"].startswith("Air Max")
    assert items[0]["suggested_color"] == "Black"
    assert items[0]["image_count"] == 1
    assert items[0]["overall_confidence"] is not None
    assert items[0]["classification_evidence"]["matched_terms"]
    assert detail["import_metadata"]["counters"]["links_out_of_scope"] == 1


def test_candidates_group_images_by_item_text():
    html = (FIXTURES / "nike-folder.html").read_text(encoding="utf-8")
    candidates, counters, pages = candidates_from_page("https://example.com/folder", "https://example.com/folder", html, 1)
    first = candidates[0]

    assert counters["links_out_of_scope"] == 1
    assert "https://example.com/folder?page=2" in pages
    assert first.title == "Nike Air Max 95 Black White"
    assert len(first.image_urls) == 2
    assert all("logo" not in image for image in first.image_urls)
    assert first.raw_metadata["grouping_confidence"] >= 0.9


def test_preview_persists_phase_two_intelligence(authed, monkeypatch):
    client, headers = authed
    brand = add_brand_and_categories(client, headers)
    pages = {
        "https://example.com/folder": (FIXTURES / "nike-folder.html").read_text(encoding="utf-8"),
        "https://example.com/folder?page=2": (FIXTURES / "nike-page-2.html").read_text(encoding="utf-8"),
    }
    monkeypatch.setattr("app.services.imports.SafeHTTPFetcher", lambda: FakeFetcher(pages))

    response = client.post("/api/imports/preview", json={"brand_id": brand["id"], "source_url": "https://example.com/folder"}, headers=headers)
    items = client.get(f"/api/imports/{response.json()['id']}/items", params={"suggested_color": "black white", "min_confidence": 0.70}).json()["items"]

    assert response.status_code == 201
    assert items
    assert items[0]["suggested_name"].startswith("Nike")
    assert items[0]["suggested_category"] == "Tenis"
    assert items[0]["suggested_model"].startswith("Air Max")
    assert items[0]["suggested_color"] in {"Black", "Black White"}
    assert items[0]["classification_confidence"] is not None
    assert items[0]["model_confidence"] is not None
    assert items[0]["color_confidence"] is not None
    assert items[0]["grouping_confidence"] is not None
    assert items[0]["classification_evidence"]["sources"]


def noop_auto_image_ingestion(monkeypatch):
    monkeypatch.setattr(
        "app.services.import_image_ingestion.ingest_import_item_images",
        lambda db, item, user: {"attempted": 0, "stored": 0, "failed": 0, "skipped": 0, "errors": []},
    )


def create_fixture_preview(client, headers, monkeypatch, fixture="nike-folder.html", auto_download=True, image_response=None):
    brand = add_brand_and_categories(client, headers)
    monkeypatch.setattr("app.services.imports.SafeHTTPFetcher", lambda: FakeFetcher({"https://example.com/folder": (FIXTURES / fixture).read_text(encoding="utf-8")}))
    if auto_download:
        if image_response is not False:
            mock_image_client(monkeypatch, image_response or (image_bytes("JPEG"), "image/jpeg"))
    else:
        noop_auto_image_ingestion(monkeypatch)
    response = client.post("/api/imports/preview", json={"brand_id": brand["id"], "source_url": "https://example.com/folder"}, headers=headers)
    assert response.status_code == 201
    import_id = response.json()["id"]
    detail = client.get(f"/api/imports/{import_id}").json()
    item = detail["items"][0]
    return brand, import_id, item


def test_preview_creates_structured_import_images_and_summaries(authed, monkeypatch):
    client, headers = authed
    before_products = client.get("/api/products").json()["pagination"]["total"]
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    after_products = client.get("/api/products").json()["pagination"]["total"]

    assert before_products == after_products
    assert len(images) == 2
    assert [image["position"] for image in images] == [0, 1]
    assert images[0]["is_cover"] is True
    assert images[0]["is_selected"] is True
    assert images[0]["status"] == "active"
    assert images[0]["width"] == 900
    assert images[0]["ingestion_status"] == "stored"
    assert images[0]["local_public_url"].startswith("/uploads/imports/")
    assert item["cover_image_url"] == images[0]["local_public_url"]
    assert item["image_count"] == 2
    assert item["image_urls"] == [image["local_public_url"] for image in images]
    assert Path(images[0]["local_storage_path"]).is_file()


def test_preview_auto_download_partial_failure_keeps_reviewable_item(authed, monkeypatch):
    client, headers = authed
    routes = {
        FIXTURE_MAIN_IMAGE: (image_bytes("JPEG"), "image/jpeg"),
        FIXTURE_SIDE_IMAGE: (b"<html>not image</html>", "image/jpeg"),
    }
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, image_response=routes)

    refreshed = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()

    assert refreshed["cover_image_url"] == images[0]["local_public_url"]
    assert images[0]["ingestion_status"] == "stored"
    assert images[1]["ingestion_status"] == "failed"
    assert images[1]["ingestion_error"] == "invalid_image_signature"
    assert refreshed["raw_metadata"]["image_ingestion"]["stored"] == 1
    assert refreshed["raw_metadata"]["image_ingestion"]["failed"] == 1


def test_preview_auto_download_retries_transient_5xx(authed, monkeypatch):
    client, headers = authed
    attempts = {FIXTURE_MAIN_IMAGE: 0, FIXTURE_SIDE_IMAGE: 0}
    original_client = httpx.Client

    def handler(request):
        url = str(request.url)
        attempts[url] = attempts.get(url, 0) + 1
        if url == FIXTURE_MAIN_IMAGE and attempts[url] == 1:
            return httpx.Response(502)
        return httpx.Response(200, content=image_bytes("PNG"), headers={"content-type": "image/png"})

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            self.client = original_client(transport=httpx.MockTransport(handler))

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr("app.services.import_image_ingestion.httpx.Client", PatchedClient)

    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, image_response=False)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()

    assert attempts[FIXTURE_MAIN_IMAGE] == 2
    assert all(image["ingestion_status"] == "stored" for image in images)


def test_preview_auto_download_does_not_retry_404(authed, monkeypatch):
    client, headers = authed
    attempts = {}
    original_client = httpx.Client

    def handler(request):
        url = str(request.url)
        attempts[url] = attempts.get(url, 0) + 1
        return httpx.Response(404)

    class PatchedClient:
        def __init__(self, *args, **kwargs):
            self.client = original_client(transport=httpx.MockTransport(handler))

        def __enter__(self):
            return self.client.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self.client.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])
    monkeypatch.setattr("app.services.import_image_ingestion.httpx.Client", PatchedClient)

    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, image_response=False)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()

    assert attempts[FIXTURE_MAIN_IMAGE] == 1
    assert all(image["ingestion_status"] == "failed" for image in images)
    assert all(image["ingestion_error"] == "source_not_found" for image in images)


def test_delete_import_removes_own_import_files(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    paths = [Path(image["local_storage_path"]) for image in images]
    assert all(path.is_file() for path in paths)

    response = client.delete(f"/api/imports/{import_id}", headers=headers)

    assert response.status_code == 204
    assert all(not path.exists() for path in paths)


def test_duplicate_and_ignored_images_are_not_persisted_as_selected_duplicates(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, "duplicate-images.html")
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()

    normalized_urls = [image["normalized_source_url"] for image in images]
    assert len(normalized_urls) == len(set(normalized_urls))
    assert len(images) == 2
    assert all("placeholder" not in image["source_url"] for image in images)
    assert images[1]["alt_text"] is None


def test_review_item_partial_update_and_review_audit(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    payload = {
        "suggested_name": "  Nike Air Max 95 Triple Black  ",
        "suggested_category_id": item["suggested_category_id"],
        "suggested_model": " Air Max 95 ",
        "suggested_color": " Triple Black ",
        "status": "reviewed",
        "updated_at": item["updated_at"],
    }

    response = client.patch(f"/api/imports/{import_id}/items/{item['id']}", json=payload, headers=headers)
    detail = client.get(f"/api/imports/{import_id}").json()

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_name"] == "Nike Air Max 95 Triple Black"
    assert data["suggested_color_normalized"] == "triple black"
    assert data["status"] == "reviewed"
    assert data["reviewed_by_id"] is not None
    assert data["reviewed_at"] is not None
    assert detail["items_reviewed"] == 1
    assert detail["items_pending"] == 1


def test_review_item_validation_errors(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)

    empty_name = client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_name": "", "status": "reviewed", "updated_at": item["updated_at"]}, headers=headers)
    missing_category = client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_category_id": 999, "updated_at": item["updated_at"]}, headers=headers)
    invalid_status = client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"status": "approved", "updated_at": item["updated_at"]}, headers=headers)

    assert empty_name.status_code == 422
    assert missing_category.status_code == 422
    assert invalid_status.status_code == 422


def test_image_review_selection_cover_fallback_and_reorder(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    first, second = images

    cannot_cover = client.patch(
        f"/api/imports/{import_id}/items/{item['id']}/images/{second['id']}",
        json={"is_selected": False, "is_cover": True, "updated_at": item["updated_at"]},
        headers=headers,
    )
    assert cannot_cover.status_code == 422

    unselect_cover = client.patch(
        f"/api/imports/{import_id}/items/{item['id']}/images/{first['id']}",
        json={"is_selected": False, "updated_at": item["updated_at"]},
        headers=headers,
    )
    assert unselect_cover.status_code == 200
    item_after = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()
    assert item_after["cover_image_url"] == second["local_public_url"]
    assert item_after["image_count"] == 1

    reordered = client.post(
        f"/api/imports/{import_id}/items/{item['id']}/images/reorder",
        json={"image_ids": [second["id"], first["id"]], "updated_at": item_after["updated_at"]},
        headers=headers,
    )
    assert reordered.status_code == 200
    assert [image["id"] for image in reordered.json()["images"]] == [second["id"], first["id"]]


def test_image_review_no_selected_images_marks_item_needs_review(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    current = item
    for image in images:
        response = client.patch(
            f"/api/imports/{import_id}/items/{item['id']}/images/{image['id']}",
            json={"is_selected": False, "updated_at": current["updated_at"]},
            headers=headers,
        )
        assert response.status_code == 200
        current = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()

    assert current["cover_image_url"] is None
    assert current["image_count"] == 0
    assert current["status"] == "needs_review"
    assert "no_selected_images" in current["warnings"]


def test_reorder_rejects_incomplete_duplicate_and_foreign_ids(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    incomplete = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/reorder", json={"image_ids": [images[0]["id"]], "updated_at": item["updated_at"]}, headers=headers)
    duplicate = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/reorder", json={"image_ids": [images[0]["id"], images[0]["id"]], "updated_at": item["updated_at"]}, headers=headers)
    foreign = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/reorder", json={"image_ids": [images[0]["id"], 999999], "updated_at": item["updated_at"]}, headers=headers)

    assert incomplete.status_code == 422
    assert duplicate.status_code == 422
    assert foreign.status_code == 422


def test_image_ingestion_stores_valid_jpeg_and_preserves_products(authed, monkeypatch, tmp_path):
    client, headers = authed
    monkeypatch.setattr(settings, "upload_directory", str(tmp_path / "uploads"))
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    image = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()[0]
    mock_image_client(monkeypatch, {image["source_url"]: (image_bytes("JPEG"), "image/jpeg")})
    before_products = client.get("/api/products").json()["pagination"]["total"]

    response = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/{image['id']}/ingest", json={"updated_at": item["updated_at"]}, headers=headers)
    after_products = client.get("/api/products").json()["pagination"]["total"]
    data = response.json()["image"]

    assert response.status_code == 200
    assert data["ingestion_status"] == "stored"
    assert data["local_mime_type"] == "image/jpeg"
    assert data["local_size_bytes"] > 0
    assert data["local_width"] == 120
    assert data["local_height"] == 120
    assert data["content_sha256"]
    assert data["local_public_url"].startswith("/uploads/imports/")
    assert Path(data["local_storage_path"]).is_file()
    assert before_products == after_products


def test_image_ingestion_blocks_private_and_unsupported_sources(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    image = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()[0]
    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["127.0.0.1"])

    response = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/{image['id']}/ingest", json={"updated_at": item["updated_at"]}, headers=headers)
    after = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()[0]

    assert response.status_code == 422
    assert "blocked_ip" in response.json()["error"]["details"]["blockers"]
    assert after["ingestion_status"] == "not_requested"


def test_image_ingestion_records_safe_failure_for_invalid_signature(authed, monkeypatch, tmp_path):
    client, headers = authed
    monkeypatch.setattr(settings, "upload_directory", str(tmp_path / "uploads"))
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    image = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()[0]
    mock_image_client(monkeypatch, {image["source_url"]: (b"<html>not image</html>", "image/jpeg")})

    response = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/{image['id']}/ingest", json={"updated_at": item["updated_at"]}, headers=headers)
    after = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()[0]

    assert response.status_code == 415
    assert after["ingestion_status"] == "failed"
    assert after["ingestion_attempts"] == 1
    assert after["ingestion_error"] == "invalid_image_signature"
    assert not list((tmp_path / "uploads").rglob("*.part"))


def test_image_ingestion_is_idempotent_and_blocks_unselected(authed, monkeypatch, tmp_path):
    client, headers = authed
    monkeypatch.setattr(settings, "upload_directory", str(tmp_path / "uploads"))
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=False)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    mock_image_client(monkeypatch, {images[0]["source_url"]: (image_bytes("PNG"), "image/png"), images[1]["source_url"]: (image_bytes("PNG"), "image/png")})

    first = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/{images[0]['id']}/ingest", json={"updated_at": item["updated_at"]}, headers=headers)
    second = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/{images[0]['id']}/ingest", json={"updated_at": item["updated_at"]}, headers=headers)
    client.patch(f"/api/imports/{import_id}/items/{item['id']}/images/{images[1]['id']}", json={"is_selected": False, "updated_at": item["updated_at"]}, headers=headers)
    current_item = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()
    blocked = client.post(f"/api/imports/{import_id}/items/{item['id']}/images/{images[1]['id']}/ingest", json={"updated_at": current_item["updated_at"]}, headers=headers)

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert blocked.status_code == 422
    assert "image_not_selected" in blocked.json()["error"]["details"]["blockers"]


def test_ingest_selected_auth_csrf_and_limit_guards(client, authed, monkeypatch):
    authed_client, headers = authed
    _, import_id, item = create_fixture_preview(authed_client, headers, monkeypatch)
    images = authed_client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    with TestClient(app) as anonymous:
        no_auth = anonymous.post(f"/api/imports/{import_id}/items/{item['id']}/images/ingest-selected", json={"image_ids": [images[0]["id"]], "updated_at": item["updated_at"]})
    no_csrf = authed_client.post(f"/api/imports/{import_id}/items/{item['id']}/images/ingest-selected", json={"image_ids": [images[0]["id"]], "updated_at": item["updated_at"]})
    duplicate = authed_client.post(f"/api/imports/{import_id}/items/{item['id']}/images/ingest-selected", json={"image_ids": [images[0]["id"], images[0]["id"]], "updated_at": item["updated_at"]}, headers=headers)

    assert no_auth.status_code == 401
    assert no_csrf.status_code == 403
    assert duplicate.status_code == 422


def test_import_review_auth_csrf_cancelled_and_stale_guards(client, authed, monkeypatch):
    authed_client, headers = authed
    _, import_id, item = create_fixture_preview(authed_client, headers, monkeypatch)
    with TestClient(app) as anonymous:
        unauth = anonymous.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_name": "Nope"})
    no_csrf = authed_client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_name": "Nope", "updated_at": item["updated_at"]})
    stale = authed_client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_name": "First", "updated_at": item["updated_at"]}, headers=headers)
    stale_again = authed_client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_name": "Second", "updated_at": item["updated_at"]}, headers=headers)

    assert unauth.status_code == 401
    assert no_csrf.status_code == 403
    assert stale.status_code == 200
    assert stale_again.status_code == 409


def reviewed_fixture_item(client, headers, monkeypatch, auto_download=True):
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch, auto_download=auto_download)
    response = client.patch(
        f"/api/imports/{import_id}/items/{item['id']}",
        json={
            "suggested_name": item["suggested_name"],
            "suggested_category_id": item["suggested_category_id"],
            "status": "reviewed",
            "updated_at": item["updated_at"],
        },
        headers=headers,
    )
    assert response.status_code == 200
    return import_id, response.json()


def test_publication_readiness_and_approval_flow(authed, monkeypatch):
    client, headers = authed
    import_id, item = reviewed_fixture_item(client, headers, monkeypatch)

    readiness = client.get(f"/api/imports/{import_id}/items/{item['id']}/publication-readiness").json()
    approved = client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": item["updated_at"]}, headers=headers)
    detail = client.get(f"/api/imports/{import_id}").json()
    unapproved = client.post(f"/api/imports/{import_id}/items/{item['id']}/unapprove", json={"updated_at": approved.json()["updated_at"]}, headers=headers)

    assert readiness["ready"] is True
    assert "image_ingestion_required" not in readiness["blockers"]
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by_id"] is not None
    assert approved.json()["approved_at"] is not None
    assert detail["items_approved"] == 1
    assert unapproved.status_code == 200
    assert unapproved.json()["status"] == "reviewed"
    assert unapproved.json()["approved_by_id"] is None


def test_approval_requires_reviewed_valid_item(authed, monkeypatch):
    client, headers = authed
    _, import_id, item = create_fixture_preview(client, headers, monkeypatch)

    not_reviewed = client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": item["updated_at"]}, headers=headers)
    missing_name = client.patch(f"/api/imports/{import_id}/items/{item['id']}", json={"suggested_name": None, "updated_at": item["updated_at"]}, headers=headers)
    item_after = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()
    reviewed_without_name = client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": item_after["updated_at"]}, headers=headers)

    assert not_reviewed.status_code == 409
    assert missing_name.status_code == 200
    assert reviewed_without_name.status_code in {409, 422}


def test_publish_blocks_external_images_and_preserves_products(authed, monkeypatch):
    client, headers = authed
    import_id, item = reviewed_fixture_item(client, headers, monkeypatch, auto_download=False)
    approved = client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": item["updated_at"]}, headers=headers).json()
    before_products = client.get("/api/products").json()["pagination"]["total"]
    before_images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()

    published = client.post(f"/api/imports/{import_id}/items/{item['id']}/publish", json={"updated_at": approved["updated_at"]}, headers=headers)
    after_products = client.get("/api/products").json()["pagination"]["total"]
    item_after = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()

    assert before_images
    assert published.status_code == 422
    assert published.json()["error"]["code"] == "IMPORT_PUBLISH_BLOCKED"
    assert "image_ingestion_required" in published.json()["error"]["details"]["blockers"]
    assert after_products == before_products
    assert item_after["published_product_id"] is None
    assert item_after["status"] == "approved"


def test_publish_after_ingestion_creates_product_images_without_variants_or_inventory(authed, monkeypatch, tmp_path):
    client, headers = authed
    monkeypatch.setattr(settings, "upload_directory", str(tmp_path / "uploads"))
    import_id, item = reviewed_fixture_item(client, headers, monkeypatch)
    images = client.get(f"/api/imports/{import_id}/items/{item['id']}/images").json()
    refreshed = client.get(f"/api/imports/{import_id}/items/{item['id']}").json()
    readiness = client.get(f"/api/imports/{import_id}/items/{item['id']}/publication-readiness").json()
    approved = client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": refreshed["updated_at"]}, headers=headers).json()

    published = client.post(f"/api/imports/{import_id}/items/{item['id']}/publish", json={"updated_at": approved["updated_at"]}, headers=headers)
    product = client.get(f"/api/products/{published.json()['product_id']}").json()

    assert readiness["ready"] is True
    assert published.status_code == 200
    assert published.json()["created"] is True
    assert product["status"] == "draft"
    assert product["visibility"] == "hidden"
    assert product["price"] == "0.00"
    assert product["track_inventory"] is False
    assert product["stock_quantity"] == 0
    assert product["variants"] == []
    assert len(product["images"]) == len(images)
    assert all(image["public_url"].startswith("/uploads/products/") for image in product["images"])
    assert len(list((tmp_path / "uploads" / "products" / product["public_id"]).iterdir())) == len(images)


def test_publish_auth_and_csrf_guards(client, authed, monkeypatch):
    authed_client, headers = authed
    import_id, item = reviewed_fixture_item(authed_client, headers, monkeypatch)
    approved = authed_client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": item["updated_at"]}, headers=headers).json()
    with TestClient(app) as anonymous:
        no_auth_approve = anonymous.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": item["updated_at"]})
        no_auth_publish = anonymous.post(f"/api/imports/{import_id}/items/{item['id']}/publish", json={"updated_at": approved["updated_at"]})
    no_csrf_approve = authed_client.post(f"/api/imports/{import_id}/items/{item['id']}/approve", json={"updated_at": approved["updated_at"]})
    no_csrf_publish = authed_client.post(f"/api/imports/{import_id}/items/{item['id']}/publish", json={"updated_at": approved["updated_at"]})

    assert no_auth_approve.status_code == 401
    assert no_auth_publish.status_code == 401
    assert no_csrf_approve.status_code == 403
    assert no_csrf_publish.status_code == 403


def test_preview_blocks_duplicate_brand_and_folder(authed, monkeypatch):
    client, headers = authed
    brand = add_brand_and_categories(client, headers)
    monkeypatch.setattr("app.services.imports.SafeHTTPFetcher", lambda: FakeFetcher({"https://example.com/folder": folder_html()}))
    first = client.post("/api/imports/preview", json={"brand_id": brand["id"], "source_url": "https://example.com/folder"}, headers=headers)
    second = client.post("/api/imports/preview", json={"brand_id": brand["id"], "source_url": "https://example.com/folder/"}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409


def test_preview_handles_pagination_loop_and_limits(authed, monkeypatch):
    client, headers = authed
    brand = add_brand_and_categories(client, headers)
    pages = {
        "https://example.com/folder": folder_html(next_page=True),
        "https://example.com/folder?page=2": '<html><body><a href="/folder?page=2">loop</a><a href="/folder/hoodie">Nike hoodie</a><img src="/folder/img/hoodie.jpg" alt="hoodie" /></body></html>',
    }
    fetcher = FakeFetcher(pages)
    monkeypatch.setattr("app.services.imports.SafeHTTPFetcher", lambda: fetcher)
    response = client.post("/api/imports/preview", json={"brand_id": brand["id"], "source_url": "https://example.com/folder"}, headers=headers)
    detail = client.get(f"/api/imports/{response.json()['id']}").json()
    assert response.status_code == 201
    assert detail["current_page"] <= 2
    assert len(set(fetcher.calls)) == len(fetcher.calls)


def test_mutating_import_routes_require_auth_and_csrf(client):
    assert client.get("/api/imports").status_code == 401
    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"})
    assert login.status_code == 200
    response = client.post("/api/imports/preview", json={"brand_id": 1, "source_url": "https://example.com/folder"})
    assert response.status_code == 403
