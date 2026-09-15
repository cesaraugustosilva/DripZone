import json
from pathlib import Path

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.products import serialize_public_product
from scripts import import_yupoo_batch as batch


def make_image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 10), "white").save(path)


def write_source(root: Path, album_id="221346032"):
    run = root / "run"
    images = run / "images"
    names = ["003242.jpg", "003243.jpg", "003278.jpg", "003279.jpg", "003319.jpg", "003320.jpg", "003233.png", "003234.png"]
    for name in names:
        make_image(images / name)
    album = {
        "album_id": album_id,
        "album_url": f"https://example.test/albums/{album_id}",
        "title": "TOP ¥158 TROUSERS ¥128 N*K* HOODIE TROUSERS 21122701001",
        "image_files": [f"images/{name}" for name in names],
    }
    manifest = [
        {
            "file": f"images/{name}",
            "sha256": f"{index:064x}",
            "mime": "image/png" if name.endswith(".png") else "image/jpeg",
            "width": 12,
            "height": 10,
            "source_url": f"https://photo.example/{name}",
            "album_id": album_id,
            "album_url": album["album_url"],
            "album_title": album["title"],
            "position": index,
        }
        for index, name in enumerate(names, start=1)
    ]
    (run / "albums.json").write_text(json.dumps([album]), encoding="utf-8")
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def sqlite_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'batch.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def one_ready_item(tmp_path: Path, monkeypatch):
    write_source(tmp_path)
    album_plans = [
        {
            "album_id": "221346032",
            "brand": "Nike",
            "category": "Conjuntos",
            "type": "Hoodie Zip e Jogger",
            "source_model": "21122701001",
            "source_price": {"top": "¥158"},
            "sizes": ["M", "L"],
            "size_charts": ["003233.png", "003234.png"],
            "colorways": [{"color": "Blue / Black", "slug": "blue-black", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg"]}],
        }
    ]
    return batch.build_plan(source_root=tmp_path, max_products=50, album_plans=album_plans)["products"][0]


def test_dry_run_builds_color_as_product_and_size_as_variant(tmp_path, monkeypatch):
    write_source(tmp_path)
    album_plans = [
        {
            "album_id": "221346032",
            "brand": "Nike",
            "category": "Conjuntos",
            "type": "Hoodie Zip e Jogger",
            "source_model": "21122701001",
            "source_price": {"top": "¥158"},
            "sizes": ["M", "L"],
            "size_charts": ["003233.png", "003234.png"],
            "colorways": [{"color": "Blue / Black", "slug": "blue-black", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg"]}],
        }
    ]

    plan = batch.build_plan(source_root=tmp_path, max_products=50, album_plans=album_plans)

    assert len(plan["products"]) == 1
    product = plan["products"][0]
    assert product["name"] == "Nike Hoodie Zip e Jogger Blue / Black"
    assert product["sizes"] == ["M", "L"]
    assert product["import_status"] == "READY"
    assert product["gallery"] == ["003242.jpg", "003243.jpg", "003278.jpg", "003233.png", "003234.png"]


def test_max_products_skips_album_that_would_exceed_limit(tmp_path, monkeypatch):
    write_source(tmp_path)
    album_plans = [
        {
            "album_id": "221346032",
            "brand": "Nike",
            "category": "Conjuntos",
            "type": "Hoodie",
            "source_model": "CODE",
            "source_price": {},
            "sizes": ["M"],
            "size_charts": [],
            "colorways": [
                {"color": "Black", "slug": "black", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg"]},
                {"color": "White", "slug": "white", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg"]},
            ],
        }
    ]

    plan = batch.build_plan(source_root=tmp_path, max_products=1, album_plans=album_plans)

    assert plan["products"] == []
    assert plan["skips"][0]["reason"] == "SKIP_LIMIT_WOULD_BE_EXCEEDED"


def test_duplicate_check_marks_existing_slug(tmp_path):
    TestingSessionLocal = sqlite_session(tmp_path)

    with TestingSessionLocal() as session:
        existing = batch.Product(name="Nike Hoodie Black", slug="nike-hoodie-code-black", public_id="p1")
        session.add(existing)
        session.commit()

        status = batch.validate_duplicate_status(session, {"slug": "nike-hoodie-code-black", "name": "Nike Hoodie Black", "brand": "Nike"})

    assert status == "JA_EXISTENTE"


def test_missing_or_ambiguous_item_is_sent_to_review(tmp_path, monkeypatch):
    write_source(tmp_path)
    album_plans = [
        {
            "album_id": "221346032",
            "brand": "Nike",
            "category": "Conjuntos",
            "type": "Hoodie",
            "source_model": "CODE",
            "source_price": {},
            "sizes": [],
            "size_charts": [],
            "colorways": [{"color": "Black", "slug": "black", "cover": "003242.jpg", "gallery": ["missing.jpg"]}],
        }
    ]

    plan = batch.build_plan(source_root=tmp_path, max_products=50, album_plans=album_plans)

    assert plan["products"][0]["import_status"] == "REVIEW"
    assert "SKIP_SIZES_UNKNOWN" in plan["products"][0]["review_reasons"]
    assert "REVIEW_NOT_ENOUGH_IMAGES" in plan["products"][0]["review_reasons"]
    assert "REVIEW_MISSING_IMAGES" in plan["products"][0]["review_reasons"]


def test_import_creates_hidden_draft_with_size_variants_and_no_public_catalog_write(tmp_path, monkeypatch):
    TestingSessionLocal = sqlite_session(tmp_path)
    item = one_ready_item(tmp_path, monkeypatch)
    products_json = batch.products_json_state()
    monkeypatch.setattr(batch.settings, "upload_directory", tmp_path / "uploads")
    monkeypatch.setenv("DRIPZONE_ALLOW_HOST_UPLOAD_WRITES", "1")

    with TestingSessionLocal() as session:
        result = batch.import_product(session, item)
        product = session.query(batch.Product).filter_by(slug=item["slug"]).one()

        assert result["status"] == "CREATED"
        assert product.status == "draft"
        assert product.visibility == "hidden"
        assert product.availability == "unavailable"
        assert str(product.price) == "0.00"
        assert [variant.size for variant in product.variants] == ["M", "L"]
        assert [variant.color for variant in product.variants] == [None, None]
        assert len(product.images) == 5
        assert sum(image.is_primary for image in product.images) == 1
        assert all(Path(image.storage_path).exists() for image in product.images)

    assert batch.products_json_state() == products_json


def test_import_rolls_back_product_and_copied_files_on_image_failure(tmp_path, monkeypatch):
    TestingSessionLocal = sqlite_session(tmp_path)
    item = one_ready_item(tmp_path, monkeypatch)
    item["images"][1]["source_path"] = str(tmp_path / "run" / "images" / "does-not-exist.jpg")
    item["gallery"][1] = "does-not-exist.jpg"
    monkeypatch.setattr(batch.settings, "upload_directory", tmp_path / "uploads")
    monkeypatch.setenv("DRIPZONE_ALLOW_HOST_UPLOAD_WRITES", "1")

    with TestingSessionLocal() as session:
        try:
            batch.import_product(session, item)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError")

        assert session.query(batch.Product).filter_by(slug=item["slug"]).count() == 0
        assert list((tmp_path / "uploads").glob("products/*/*")) == []


def test_import_is_idempotent_for_same_item(tmp_path, monkeypatch):
    TestingSessionLocal = sqlite_session(tmp_path)
    item = one_ready_item(tmp_path, monkeypatch)
    monkeypatch.setattr(batch.settings, "upload_directory", tmp_path / "uploads")
    monkeypatch.setenv("DRIPZONE_ALLOW_HOST_UPLOAD_WRITES", "1")

    with TestingSessionLocal() as session:
        first = batch.import_product(session, item)
        second = batch.import_product(session, item)

        assert first["status"] == "CREATED"
        assert second["status"] == "SKIPPED_ALREADY_EXISTS"
        assert session.query(batch.Product).filter_by(slug=item["slug"]).count() == 1


def test_one_size_plan_uses_official_single_size(tmp_path):
    write_source(tmp_path)
    album_plans = [
        batch.one_size_album(
            album_id="221346032",
            brand="Supreme",
            category="Acessórios",
            type="Beanie",
            source_model="OS",
            source_price={"hat": "¥105"},
            colorways=[{"color": "Black", "slug": "black", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg"]}],
        )
    ]

    plan = batch.build_plan(source_root=tmp_path, max_products=50, batch_id="test", album_plans=album_plans)

    assert plan["products"][0]["sizes"] == [batch.ONE_SIZE_VALUE]
    assert plan["products"][0]["import_status"] == "READY"


def test_one_size_import_and_public_serialization(tmp_path, monkeypatch):
    TestingSessionLocal = sqlite_session(tmp_path)
    write_source(tmp_path)
    album_plans = [
        batch.one_size_album(
            album_id="221346032",
            brand="Supreme",
            category="Acessórios",
            type="Beanie",
            source_model="OS",
            source_price={"hat": "¥105"},
            colorways=[{"color": "Black", "slug": "black", "cover": "003242.jpg", "gallery": ["003242.jpg", "003243.jpg", "003278.jpg"]}],
        )
    ]
    item = batch.build_plan(source_root=tmp_path, max_products=50, batch_id="test", album_plans=album_plans)["products"][0]
    monkeypatch.setattr(batch.settings, "upload_directory", tmp_path / "uploads")
    monkeypatch.setenv("DRIPZONE_ALLOW_HOST_UPLOAD_WRITES", "1")

    with TestingSessionLocal() as session:
        result = batch.import_product(session, item)
        product = session.query(batch.Product).filter_by(slug=item["slug"]).one()
        public_payload = serialize_public_product(product)

        assert result["status"] == "CREATED"
        assert [variant.size for variant in product.variants] == [batch.ONE_SIZE_VALUE]
        assert product.variants[0].stock_quantity == 0
        assert product.variants[0].color is None
        assert public_payload["sizes"] == [batch.ONE_SIZE_VALUE]
