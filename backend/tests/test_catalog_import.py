import json
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from app.services.catalog_import import (
    CatalogBrand,
    CatalogImageDownloader,
    CatalogImporter,
    CatalogSourceProduct,
    CatalogYupooScanner,
    DeterministicProductEnrichmentProvider,
    atomic_write_json,
    detect_censored_brands,
    extract_supplier_code,
    extract_supplier_metadata,
    is_bad_supplier_name,
    product_folder_name,
    remove_supplier_noise,
    stable_product_id,
)
from app.services.import_image_ingestion import is_allowed_yupoo_media_host, validate_yupoo_media_url
from app.services.imports import FetchedPage, candidates_from_page, detect_yupoo_page_type, extract_yupoo_album_product

FIXTURES = Path(__file__).parent / "fixtures" / "imports"


def image_bytes(fmt="JPEG", size=(120, 120)):
    data = BytesIO()
    Image.new("RGB", size, "white").save(data, format=fmt)
    return data.getvalue()


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url):
        key = str(url).rstrip("/")
        self.calls.append(key)
        return FetchedPage(url=key, body=self.pages[key], content_type="text/html", status_code=200)


class FakeDownloader:
    def download_images(self, image_urls, product_dir, existing_product, force=False, album_url=None):
        product_dir.mkdir(parents=True, exist_ok=True)
        assets = []
        for index, url in enumerate(image_urls):
            filename = "cover.jpg" if index == 0 else f"{index:02d}.jpg"
            (product_dir / filename).write_bytes(image_bytes())
            assets.append(type("Asset", (), {"filename": filename, "position": index, "sha256": f"sha{index}", "mime_type": "image/jpeg", "width": 120, "height": 120, "source_url": url, "size_bytes": 100, "created": True})())
        return assets, []


class ConfigurableDownloader:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def download_images(self, image_urls, product_dir, existing_product, force=False, album_url=None):
        self.calls.append({"image_urls": image_urls, "product_dir": product_dir, "existing_product": existing_product})
        product_dir.mkdir(parents=True, exist_ok=True)
        assets = []
        failures = []
        plan = self.results.pop(0)
        for index in range(plan.get("assets", 0)):
            filename = "cover.jpg" if index == 0 else f"{index:02d}.jpg"
            (product_dir / filename).write_bytes(image_bytes())
            assets.append(type("Asset", (), {"filename": filename, "position": index, "sha256": f"sha{index}", "mime_type": "image/jpeg", "width": 120, "height": 120, "source_url": image_urls[index], "size_bytes": 100, "created": plan.get("created", True)})())
        for index in range(plan.get("failures", 0)):
            failures.append({"image_url": image_urls[index], "album_url": album_url, "host": "photo.yupoo.com", "attempt": 1, "error_type": "source_error", "status_code": 567, "message": "CDN returned HTML", "error": "source_error"})
        return assets, failures


def product(title, image_urls=None):
    url = f"https://example.com/folder/{title.lower().replace(' ', '-')}"
    return CatalogSourceProduct(url, url, stable_product_id(url), title, "", image_urls or ["https://example.com/img.jpg"], raw_metadata={})


def test_stable_id_and_folder_name_are_deterministic():
    source = "https://example.com/folder/Nike-Tee?utm_source=x"
    assert stable_product_id(source) == stable_product_id("https://example.com/folder/Nike-Tee")
    assert product_folder_name("Nike Multi Logo Tee Preta", "a1b2c3d4").endswith("-a1b2c3")


def test_name_quality_and_standardization():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Chrome Hearts", "chrome-hearts")
    assert is_bad_supplier_name("A12345")
    assert is_bad_supplier_name("New Item")
    assert not is_bad_supplier_name("CH Multi Cross Tee BK 24SS")
    name = provider.assess_name(product("CH Multi Cross Tee BK 24SS"), brand)
    assert name.supplier_name == "CH Multi Cross Tee BK 24SS"
    assert name.final_name == "Chrome Hearts Multi Cross Tee Preta"


def test_category_classification_matrix_and_low_confidence():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Nike", "nike")
    cases = {
        "Nike Logo Tee": "camisetas",
        "Nike Cargo Pants": "calcas",
        "Nike Zip Hoodie": "moletons",
        "Nike Windbreaker Jacket": "jaquetas",
        "Nike Shorts": "shorts",
        "Nike Tracksuit Set": "conjuntos",
        "Nike Cap": "acessorios",
        "Gucci Jewelry55073004": "acessorios",
        "Nike Air Max Sneaker": "calcados",
        "ABC123": "desconhecidos",
    }
    for title, slug in cases.items():
        assert provider.classify_category(product(title), brand).slug == slug


def test_scanner_opens_each_product_page():
    pages = {
        "https://example.com/folder": """
          <html><head><title>Folder</title></head><body>
            <a href="/folder/tee">Nike Tee</a>
            <img src="/folder/thumb.jpg" alt="thumb" />
          </body></html>
        """,
        "https://example.com/folder/tee": """
          <html><head><title>Nike Multi Logo Tee</title></head><body>
            <img src="/folder/tee/01.jpg" alt="Nike tee front" />
            <img src="/folder/tee/02.jpg" alt="Nike tee back" />
          </body></html>
        """,
    }
    scanner = CatalogYupooScanner(FakeFetcher(pages), max_products=5)
    products = scanner.scan("https://example.com/folder")
    assert len(products) == 1
    assert products[0].supplier_name == "Nike Multi Logo Tee"
    assert len(products[0].image_urls) == 2


def test_product_json_metadata_manifest_idempotency_and_dry_run(tmp_path):
    brand = CatalogBrand("Nike", "nike")
    source = product("Nike Multi Logo Tee")
    scanner = type("Scanner", (), {"scan": lambda self, url: [source]})()
    importer = CatalogImporter(catalog_path=tmp_path, scanner=scanner, downloader=FakeDownloader())
    dry = importer.run(brand=brand, folder_url="https://example.com/folder", dry_run=True)
    assert dry["products_found"] == 1
    assert not (tmp_path / "nike").exists()
    first = importer.run(brand=brand, folder_url="https://example.com/folder")
    second = importer.run(brand=brand, folder_url="https://example.com/folder")
    product_json = next((tmp_path / "nike").glob("*/*/product.json"))
    metadata = json.loads((tmp_path / "nike" / "_metadata.json").read_text(encoding="utf-8"))
    manifest = json.loads(next((tmp_path / "_runs").glob("*.json")).read_text(encoding="utf-8"))
    assert first["products_created"] == 1
    assert second["products_skipped"] == 1
    assert metadata["stats"]["total_products"] == 1
    assert manifest["importer_version"]
    assert json.loads(product_json.read_text(encoding="utf-8"))["images"]["cover"] == "cover.jpg"


def test_real_downloader_partial_failure_and_local_skip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"])
    routes = {
        "https://photo.yupoo.com/husky/ok/medium.jpg": httpx.Response(200, content=image_bytes("JPEG"), headers={"content-type": "image/jpeg"}),
        "https://photo.yupoo.com/husky/bad/medium.jpg": httpx.Response(200, content=b"not image", headers={"content-type": "image/jpeg"}),
    }
    attempts = {}

    def handler(request):
        attempts[str(request.url)] = attempts.get(str(request.url), 0) + 1
        return routes[str(request.url)]

    def factory():
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    downloader = CatalogImageDownloader(client_factory=factory)
    assets, failures = downloader.download_images(["https://photo.yupoo.com/husky/ok/medium.jpg", "https://photo.yupoo.com/husky/bad/medium.jpg"], tmp_path, None, album_url="https://seller.x.yupoo.com/albums/1")
    existing = {"images": {"items": [{"filename": assets[0].filename, "sha256": assets[0].sha256, "source_url": "https://photo.yupoo.com/husky/ok/medium.jpg"}]}}
    assets_again, _ = downloader.download_images(["https://photo.yupoo.com/husky/ok/medium.jpg"], tmp_path, existing, album_url="https://seller.x.yupoo.com/albums/1")
    assert len(assets) == 1
    assert failures[0]["error"] == "invalid_image_signature"
    assert attempts["https://photo.yupoo.com/husky/ok/medium.jpg"] == 1
    assert assets_again[0].created is False


def test_yupoo_media_policy_headers_redirects_and_failures(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.import_image_ingestion.resolve_hostname", lambda hostname: ["93.184.216.34"] if hostname != "private.test" else ["127.0.0.1"])
    assert is_allowed_yupoo_media_host("photo.yupoo.com")
    assert is_allowed_yupoo_media_host("pic.yupoo.com")
    assert not is_allowed_yupoo_media_host("evil.example")
    assert validate_yupoo_media_url("https://photo.yupoo.com/husky/ok/medium.jpg")
    try:
        validate_yupoo_media_url("https://evil.example/image.jpg")
    except Exception as exc:
        assert "host_not_allowed" in str(exc)

    requests = []
    attempts = {"timeout": 0, "transient": 0, "missing": 0}

    def handler(request):
        requests.append(request)
        url = str(request.url)
        if "redirect-ok" in url:
            return httpx.Response(302, headers={"location": "https://photo.yupoo.com/husky/ok/medium.jpg"})
        if "redirect-private" in url:
            return httpx.Response(302, headers={"location": "https://private.test/image.jpg"})
        if "html" in url:
            return httpx.Response(200, content=b"<html></html>", headers={"content-type": "text/html"})
        if "empty" in url:
            return httpx.Response(200, content=b"", headers={"content-type": "image/jpeg"})
        if "timeout" in url:
            attempts["timeout"] += 1
            if attempts["timeout"] == 1:
                raise httpx.TimeoutException("timeout")
        if "transient" in url:
            attempts["transient"] += 1
            if attempts["transient"] == 1:
                return httpx.Response(503, content=b"down", headers={"content-type": "text/plain"})
        if "missing" in url:
            attempts["missing"] += 1
            return httpx.Response(404)
        return httpx.Response(200, content=image_bytes("PNG"), headers={"content-type": "image/png"})

    def factory():
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    downloader = CatalogImageDownloader(client_factory=factory)
    album = "https://seller.x.yupoo.com/albums/1"
    assets, failures = downloader.download_images(
        [
            "https://photo.yupoo.com/husky/ok/medium.jpg",
            "https://photo.yupoo.com/husky/html/medium.jpg",
            "https://photo.yupoo.com/husky/empty/medium.jpg",
            "https://photo.yupoo.com/husky/redirect-ok/medium.jpg",
            "https://photo.yupoo.com/husky/redirect-private/medium.jpg",
            "https://photo.yupoo.com/husky/timeout/medium.jpg",
            "https://photo.yupoo.com/husky/transient/medium.jpg",
            "https://photo.yupoo.com/husky/missing/medium.jpg",
        ],
        tmp_path,
        None,
        album_url=album,
    )
    assert len(assets) == 4
    failure_types = {item["error_type"] for item in failures}
    assert {"invalid_content_type", "empty_file", "blocked_ip", "source_not_found"} <= failure_types
    assert attempts["timeout"] == 2
    assert attempts["transient"] == 2
    assert attempts["missing"] == 1
    first = requests[0]
    assert first.headers["referer"] == album
    assert "Mozilla" in first.headers["user-agent"]
    assert "image/" in first.headers["accept"]


def test_atomic_write_keeps_valid_json(tmp_path):
    path = tmp_path / "data.json"
    atomic_write_json(path, {"ok": True})
    atomic_write_json(path, {"ok": False})
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": False}


def test_yupoo_category_discovers_only_album_links_and_ignores_navigation():
    html = (FIXTURES / "yupoo-category-realistic.html").read_text(encoding="utf-8")
    candidates, counters, pages = candidates_from_page("https://huskyreps.x.yupoo.com/categories/5003171", "https://huskyreps.x.yupoo.com/categories/5003171", html, 1)
    assert detect_yupoo_page_type("https://huskyreps.x.yupoo.com/categories/5003171", html) == "category_page"
    assert len(candidates) == 3
    assert counters["albums_found_before_dedupe"] == 4
    assert counters["albums_duplicates_removed"] == 1
    assert pages == ["https://huskyreps.x.yupoo.com/categories/5003171?page=2"]
    assert all("/albums/" in item.source_url for item in candidates)
    assert all("/categories/" not in item.source_url for item in candidates)
    assert candidates[0].title == "￥~135 DIAS TROUSERS 66070714"
    assert "Supplier Product Catalog" not in candidates[0].title


def test_yupoo_max_products_applies_after_album_filtering():
    html = (FIXTURES / "yupoo-category-realistic.html").read_text(encoding="utf-8")
    pages = {
        "https://huskyreps.x.yupoo.com/categories/5003171": html,
        "https://huskyreps.x.yupoo.com/albums/244951586?isSubCate=false&referrercate=5003171&uid=1": (FIXTURES / "yupoo-album-realistic.html").read_text(encoding="utf-8"),
        "https://huskyreps.x.yupoo.com/albums/244951578?isSubCate=false&referrercate=5003171&uid=1": (FIXTURES / "yupoo-album-realistic.html").read_text(encoding="utf-8").replace("66070714", "66070713"),
        "https://huskyreps.x.yupoo.com/albums/244951430?isSubCate=false&referrercate=5003171&uid=1": (FIXTURES / "yupoo-album-realistic.html").read_text(encoding="utf-8").replace("TROUSERS 66070714", "T-SHIRT 77070740"),
    }
    scanner = CatalogYupooScanner(FakeFetcher(pages), max_products=2)
    products = scanner.scan("https://huskyreps.x.yupoo.com/categories/5003171")
    assert len(products) == 2
    assert scanner.last_scan_stats["albums_valid"] == 3
    assert scanner.last_scan_stats["products_to_process"] == 2


def test_yupoo_album_extracts_specific_title_and_gallery_images():
    html = (FIXTURES / "yupoo-album-realistic.html").read_text(encoding="utf-8")
    product = extract_yupoo_album_product("https://huskyreps.x.yupoo.com/albums/244951586?uid=1", html, category_title="DIAS | 分类 | husky-reps | Supplier Product Catalog")
    assert detect_yupoo_page_type("https://huskyreps.x.yupoo.com/albums/244951586?uid=1", html) == "album_page"
    assert product.title == "￥~135 DIAS TROUSERS 66070714"
    assert "Supplier Product Catalog" not in product.title
    assert product.image_urls == [
        "https://photo.yupoo.com/huskyreps/0398195285/medium.jpg",
        "https://photo.yupoo.com/huskyreps/e7277a2271/medium.jpg",
        "https://photo.yupoo.com/huskyreps/505f161ec4/medium.jpg",
    ]
    assert all("qrcode" not in url and "logo" not in url and "other" not in url for url in product.image_urls)


def test_yupoo_dry_run_manifest_shows_found_images_and_brand_warning(tmp_path):
    brand = CatalogBrand("Adidas", "adidas")
    source = product("￥~135 DIAS TROUSERS 66070714", ["https://photo.yupoo.com/huskyreps/0398195285/medium.jpg"] * 3)
    scanner = type("Scanner", (), {"last_scan_stats": {"albums_found_before_dedupe": 4, "albums_valid": 3, "albums_duplicates_removed": 1, "products_to_process": 1}, "scan": lambda self, url: [source]})()
    importer = CatalogImporter(catalog_path=tmp_path, scanner=scanner, downloader=FakeDownloader())
    manifest = importer.run(brand=brand, folder_url="https://example.com/folder", dry_run=True)
    assert manifest["items"][0]["source_images"] == 3
    assert manifest["items"][0]["images"] == 0
    assert "possible_brand_divergence" in manifest["warnings"]
    assert not (tmp_path / "adidas").exists()


def test_supplier_title_cleanup_metadata_codes_and_censored_brands():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    title = "￥~189 🔥DI🔥AS HOODIE 66073029 (im 185CM 80KG iwear size XL in the photo)"
    source = product(title)
    name = provider.assess_name(source, brand)
    category = provider.classify_category(source, brand)
    assert name.supplier_name == title
    assert name.generated_name == "Adidas Hoodie"
    assert name.final_name == "Adidas Hoodie"
    assert name.supplier_code == "66073029"
    assert name.supplier_metadata == {"model_height_cm": 185, "model_weight_kg": 80, "model_wearing_size": "XL"}
    assert name.supplier_code not in name.final_name
    assert category.slug == "moletons"
    assert category.confidence == 0.95
    assert source.raw_metadata == {}
    assert extract_supplier_code(title) == "66073029"
    assert extract_supplier_metadata(title)["model_wearing_size"] == "XL"
    assert detect_censored_brands("DI🔥AS", brand) == ["Adidas"]


def test_jacket_trousers_set_name_category_code_and_supplier_name():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    title = "￥ ~ 269 🔥DI🔥AS JACKET TROUSERS 55072722"
    source = product(title)
    name = provider.assess_name(source, brand)
    category = provider.classify_category(source, brand)
    assert name.supplier_name == title
    assert name.final_name == "Adidas Jacket And Trousers Set"
    assert name.supplier_code == "55072722"
    assert name.supplier_code not in name.final_name
    assert category.slug == "conjuntos"
    assert category.confidence == 0.95
    assert category.needs_review is False


def test_supplier_price_prefix_supports_legitimate_currency_symbols_without_mojibake():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    samples = [
        "￥ ~ 269 Adidas JACKET TROUSERS 55072722",
        "¥~269 Adidas JACKET TROUSERS 55072722",
        "$269 Adidas JACKET TROUSERS 55072722",
        "€269 Adidas JACKET TROUSERS 55072722",
        "£269 Adidas JACKET TROUSERS 55072722",
        "\u00ef\u00bf\u00a5~269 Adidas JACKET TROUSERS 55072722",
        "\u00c3\u00af\u00c2\u00bf\u00c2\u00a5~269 Adidas JACKET TROUSERS 55072722",
    ]

    for title in samples:
        assert remove_supplier_noise(title).startswith("Adidas JACKET TROUSERS")
        assert provider.assess_name(product(title), brand).final_name == "Adidas Jacket And Trousers Set"


def test_sweater_crewneck_pullover_and_sweatshirt_are_moletons():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    for term in ["SWEATER", "CREWNECK", "PULLOVER", "SWEATSHIRT"]:
        source = product(f"￥~139 🔥DI🔥AS {term} 66072718")
        name = provider.assess_name(source, brand)
        category = provider.classify_category(source, brand)
        assert name.supplier_name == source.supplier_name
        assert name.supplier_code == "66072718"
        assert category.slug == "moletons"
        assert category.confidence == 0.95


def test_unknown_brand_token_near_ampersand_is_preserved_and_flagged():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    title = "￥ ~288 Y🔥 & 🔥DI🔥AS TROUSERS 55072713"
    source = product(title)
    name = provider.assess_name(source, brand)
    category = provider.classify_category(source, brand)
    assert name.final_name == "Adidas Trousers"
    assert name.supplier_name == title
    assert name.supplier_code == "55072713"
    assert name.brand_conflict is True
    assert name.unrecognized_brand_tokens == ["Y🔥"]
    assert any("outra marca nao reconhecida" in note for note in name.review_notes)
    assert category.slug == "calcas"


def test_woman_audience_is_extracted_after_preserving_supplier_name():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    title = "￥~165 🔥DI🔥AS JACKET WOMAN 66072710"
    source = product(title)
    name = provider.assess_name(source, brand)
    category = provider.classify_category(source, brand)
    assert name.supplier_name == title
    assert name.supplier_code == "66072710"
    assert name.supplier_metadata["audience"] == "female"
    assert name.final_name == "Adidas Jacket"
    assert "Woman" not in name.final_name
    assert category.slug == "jaquetas"


def test_new_rules_do_not_change_existing_hoodie_and_jewelry_classification():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    hoodie = product("￥~189 🔥DI🔥AS HOODIE 66073029")
    jewelry = product("￥~219 G🔥C🔥I & 🔥DI🔥AS JEWELRY55073004")
    assert provider.assess_name(hoodie, brand).final_name == "Adidas Hoodie"
    assert provider.classify_category(hoodie, brand).slug == "moletons"
    assert provider.assess_name(jewelry, brand).final_name == "Gucci e Adidas Jewelry"
    assert provider.classify_category(jewelry, brand).slug == "acessorios"


def test_jewelry_code_split_category_and_brand_conflict():
    provider = DeterministicProductEnrichmentProvider()
    brand = CatalogBrand("Adidas", "adidas")
    title = "￥~219 G🔥C🔥I & 🔥DI🔥AS JEWELRY55073004"
    source = product(title)
    name = provider.assess_name(source, brand)
    category = provider.classify_category(source, brand)
    assert name.generated_name == "Gucci e Adidas Jewelry"
    assert name.final_name == "Gucci e Adidas Jewelry"
    assert name.supplier_code == "55073004"
    assert name.brand_conflict is True
    assert name.needs_review is True
    assert detect_censored_brands("G🔥C🔥I") == ["Gucci"]
    assert category.slug == "acessorios"
    assert category.confidence == 0.95


def test_duplicate_clean_names_keep_distinct_ids_and_need_review(tmp_path):
    brand = CatalogBrand("Adidas", "adidas")
    sources = [
        product("￥~189 🔥DI🔥AS HOODIE 66073029 (im 185CM 80KG iwear size XL in the photo)"),
        product("￥~189 🔥DI🔥AS HOODIE 66073037 (im 185CM 80KG iwear size XL in the photo)"),
    ]
    scanner = type("Scanner", (), {"last_scan_stats": {}, "scan": lambda self, url: sources})()
    importer = CatalogImporter(catalog_path=tmp_path, scanner=scanner, downloader=FakeDownloader())
    manifest = importer.run(brand=brand, folder_url="https://example.com/folder", dry_run=True)
    assert manifest["items"][0]["source_id"] != manifest["items"][1]["source_id"]
    assert manifest["items"][0]["final_name"] == "Adidas Hoodie"
    assert manifest["items"][1]["final_name"] == "Adidas Hoodie"
    for item in manifest["items"]:
        assert item["review"]["needs_name_review"] is True
        assert "Nome comercial coincide" in item["review"]["notes"][0]
        assert item["supplier_code"] not in item["final_name"]
    assert manifest["items"][0]["review"]


def test_image_result_semantics_failed_partial_created_and_metadata(tmp_path):
    brand = CatalogBrand("Adidas", "adidas")
    sources = [
        product("Adidas Hoodie", ["https://photo.yupoo.com/husky/a/medium.jpg"]),
        product("Adidas Jacket", ["https://photo.yupoo.com/husky/b/medium.jpg", "https://photo.yupoo.com/husky/c/medium.jpg"]),
        product("Adidas Shorts", ["https://photo.yupoo.com/husky/d/medium.jpg"]),
    ]
    scanner = type("Scanner", (), {"last_scan_stats": {}, "scan": lambda self, url: sources})()
    downloader = ConfigurableDownloader([{"assets": 0, "failures": 1}, {"assets": 1, "failures": 1}, {"assets": 1, "failures": 0}])
    importer = CatalogImporter(catalog_path=tmp_path, scanner=scanner, downloader=downloader)
    manifest = importer.run(brand=brand, folder_url="https://example.com/folder")
    assert [item["result"] for item in manifest["items"]] == ["failed", "partial", "created"]
    assert manifest["products_created"] == 1
    assert manifest["products_partial"] == 1
    assert manifest["products_with_error"] == 1
    assert manifest["images_found"] == 4
    assert manifest["downloaded_images"] == 2
    assert manifest["failed_images"] == 2
    failed_json = json.loads((tmp_path / manifest["items"][0]["destination"] / "product.json").read_text(encoding="utf-8"))
    assert failed_json["import"]["status"] == "failed"
    assert failed_json["import"]["errors"][0]["error_type"] == "source_error"
    assert "source_error" not in failed_json["review"]["notes"]
    metadata = json.loads((tmp_path / "adidas" / "_metadata.json").read_text(encoding="utf-8"))
    assert metadata["stats"]["total_products"] == 2
    assert metadata["last_import"]["failed_products"] == 1


def test_failed_product_can_be_resumed_without_duplicate_folder(tmp_path):
    brand = CatalogBrand("Adidas", "adidas")
    source = product("Adidas Hoodie", ["https://photo.yupoo.com/husky/a/medium.jpg"])
    scanner = type("Scanner", (), {"last_scan_stats": {}, "scan": lambda self, url: [source]})()
    first = CatalogImporter(catalog_path=tmp_path, scanner=scanner, downloader=ConfigurableDownloader([{"assets": 0, "failures": 1}]))
    first_manifest = first.run(brand=brand, folder_url="https://example.com/folder")
    second = CatalogImporter(catalog_path=tmp_path, scanner=scanner, downloader=ConfigurableDownloader([{"assets": 1, "failures": 0}]))
    second_manifest = second.run(brand=brand, folder_url="https://example.com/folder")
    assert first_manifest["items"][0]["destination"] == second_manifest["items"][0]["destination"]
    assert first_manifest["items"][0]["source_id"] == second_manifest["items"][0]["source_id"]
    assert second_manifest["items"][0]["result"] == "updated"
    assert len(list((tmp_path / "adidas").glob("*/*/product.json"))) == 1
