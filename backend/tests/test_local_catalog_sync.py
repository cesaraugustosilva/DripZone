import json
from decimal import Decimal
from io import BytesIO

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Brand, Category, ImportItem, Product, ProductImage
from app.services.local_catalog_sync import LocalCatalogSyncOptions, sync_local_catalog
from app.services.products import serialize_public_product
from app.services import local_catalog_sync


def image_bytes(fmt="PNG"):
    data = BytesIO()
    Image.new("RGB", (10, 10), "white").save(data, format=fmt)
    data.seek(0)
    return data.getvalue()


def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def write_catalog_product(root, *, product_id="stable-1", folder="adidas/shorts/adidas-shorts-abc123", final_name="Adidas Shorts", category_slug="shorts", image_names=("cover.png", "01.png")):
    product_dir = root / folder
    product_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for position, filename in enumerate(image_names):
        content = image_bytes()
        (product_dir / filename).write_bytes(content)
        items.append({
            "filename": filename,
            "position": position,
            "sha256": f"{product_id}-{position}".encode().hex()[:64],
            "mime_type": "image/png",
            "width": 10,
            "height": 10,
            "source_url": f"https://photo.example/{product_id}/{position}.png",
        })
    payload = {
        "schema_version": 1,
        "id": product_id,
        "supplier_name": f"Supplier {product_id}",
        "supplier_code": f"CODE-{product_id}",
        "generated_name": final_name,
        "final_name": final_name,
        "slug": "adidas-shorts",
        "brand": {"name": "Adidas", "slug": "adidas"},
        "category": {"name": category_slug.title(), "slug": category_slug, "confidence": 0.95},
        "description": {"supplier": "https://supplier.example/item", "generated": "", "final": "Supplier description"},
        "supplier_metadata": {"audience": "female"},
        "images": {"cover": image_names[0], "items": items},
        "import": {"status": "created", "errors": [], "images_found": len(items), "images_downloaded": len(items), "images_failed": 0},
        "source": {"provider": "yupoo", "folder_url": "https://yupoo.example/folder", "product_url": f"https://yupoo.example/{product_id}", "source_id": product_id, "imported_at": "2026-07-30T21:00:00+00:00"},
        "review": {"status": "pending", "needs_name_review": False, "needs_category_review": category_slug == "desconhecidos", "brand_conflict": False, "detected_brands": ["Adidas"], "unrecognized_brand_tokens": [], "notes": []},
    }
    (product_dir / "product.json").write_text(json.dumps(payload), encoding="utf-8")
    return product_dir / "product.json"


def test_local_catalog_sync_creates_draft_product_and_preserves_supplier_metadata(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(local_catalog_sync.settings, "upload_directory", str(uploads))
    write_catalog_product(catalog)
    SessionLocal = session_factory(tmp_path)

    with SessionLocal() as db:
        result = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))
        product = db.query(Product).one()
        item = db.query(ImportItem).one()

        assert result.created == 1
        assert product.status == "draft"
        assert product.visibility == "hidden"
        assert product.price == Decimal("0.00")
        assert serialize_public_product(product)["price"] is None
        assert product.brand.slug == "adidas"
        assert product.category.slug == "shorts"
        assert len(product.images) == 2
        assert product.images[0].public_url.startswith("/uploads/products/")
        assert ":\\" not in product.images[0].public_url
        assert item.external_id == "stable-1"
        assert item.raw_metadata["names"]["supplier_name"] == "Supplier stable-1"
        assert item.raw_metadata["supplier"]["code"] == "CODE-stable-1"
        assert item.raw_metadata["detected"]["audience"] == "female"


def test_local_catalog_sync_is_idempotent_and_preserves_manual_commercial_edits(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(local_catalog_sync.settings, "upload_directory", str(uploads))
    product_json = write_catalog_product(catalog)
    SessionLocal = session_factory(tmp_path)

    with SessionLocal() as db:
        first = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))
        product = db.query(Product).one()
        manual_brand = Brand(name="Manual Brand", slug="manual-brand")
        manual_category = Category(name="Manual Category", slug="manual-category")
        db.add_all([manual_brand, manual_category])
        db.flush()
        product.name = "Manual Name"
        product.description = "Manual description"
        product.price = Decimal("123.45")
        product.status = "published"
        product.visibility = "public"
        product.brand_id = manual_brand.id
        product.category_id = manual_category.id
        db.commit()

        payload = json.loads(product_json.read_text(encoding="utf-8"))
        payload["final_name"] = "Changed Supplier Name"
        product_json.write_text(json.dumps(payload), encoding="utf-8")
        second = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))

        assert first.created == 1
        assert second.created == 0
        assert db.query(Product).count() == 1
        assert db.query(ProductImage).count() == 2
        product = db.query(Product).one()
        assert product.name == "Manual Name"
        assert product.description == "Manual description"
        assert product.price == Decimal("123.45")
        assert product.status == "published"
        assert product.visibility == "public"
        assert product.brand.slug == "manual-brand"
        assert product.category.slug == "manual-category"
        assert db.query(ImportItem).one().suggested_name == "Changed Supplier Name"


def test_local_catalog_sync_handles_moved_product_and_new_image_without_duplicates(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(local_catalog_sync.settings, "upload_directory", str(uploads))
    write_catalog_product(catalog, product_id="stable-moved", folder="adidas/shorts/first-folder")
    SessionLocal = session_factory(tmp_path)

    with SessionLocal() as db:
        sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))
        first_folder = catalog / "adidas" / "shorts" / "first-folder"
        moved_folder = catalog / "adidas" / "jaquetas" / "moved-folder"
        moved_folder.mkdir(parents=True)
        for path in first_folder.iterdir():
            path.rename(moved_folder / path.name)
        first_folder.rmdir()
        payload = json.loads((moved_folder / "product.json").read_text(encoding="utf-8"))
        payload["category"] = {"name": "Jaquetas", "slug": "jaquetas", "confidence": 0.95}
        payload["images"]["items"].append({"filename": "02.png", "position": 2, "sha256": "new-image-sha", "mime_type": "image/png", "width": 10, "height": 10, "source_url": "https://photo.example/new.png"})
        (moved_folder / "02.png").write_bytes(image_bytes())
        (moved_folder / "product.json").write_text(json.dumps(payload), encoding="utf-8")

        result = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))

        assert result.created == 0
        assert db.query(Product).count() == 1
        assert db.query(ProductImage).count() == 3
        assert db.query(ProductImage).filter(ProductImage.is_primary == True).count() == 1


def test_local_catalog_sync_restores_missing_reused_image_file(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(local_catalog_sync.settings, "upload_directory", str(uploads))
    write_catalog_product(catalog)
    SessionLocal = session_factory(tmp_path)

    with SessionLocal() as db:
        sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))
        image = db.query(ProductImage).filter(ProductImage.is_primary == True).one()
        stored_path = local_catalog_sync.Path(image.storage_path)
        stored_path.unlink()

        result = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog))

        assert result.created == 0
        assert result.updated == 1
        assert result.unchanged == 0
        assert result.images_created == 1
        assert result.images_reused == 1
        assert db.query(Product).count() == 1
        assert db.query(ProductImage).count() == 2
        assert stored_path.exists()


def test_local_catalog_sync_dry_run_limit_and_isolated_failure(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    uploads = tmp_path / "uploads"
    public_json = tmp_path / "frontend" / "data" / "products.json"
    public_json.parent.mkdir(parents=True)
    public_json.write_text('{"products":[]}', encoding="utf-8")
    monkeypatch.setattr(local_catalog_sync.settings, "upload_directory", str(uploads))
    write_catalog_product(catalog, product_id="valid-1", folder="adidas/shorts/valid")
    invalid_dir = catalog / "adidas" / "shorts" / "zz-invalid"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "product.json").write_text(json.dumps({"schema_version": 1, "final_name": "Invalid"}), encoding="utf-8")
    SessionLocal = session_factory(tmp_path)

    with SessionLocal() as db:
        dry = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog, dry_run=True, limit=1))
        assert dry.found == 1
        assert dry.created == 1
        assert db.query(Product).count() == 0
        assert not uploads.exists()

        real = sync_local_catalog(db, LocalCatalogSyncOptions(catalog_root=catalog, limit=2))
        assert real.found == 2
        assert real.created == 1
        assert real.failed == 1
        assert db.query(Product).count() == 1
        assert public_json.read_text(encoding="utf-8") == '{"products":[]}'
