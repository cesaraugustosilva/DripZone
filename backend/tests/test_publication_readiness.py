from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Brand, Category, ImportItem, ImportRecord, Product, ProductImage
from app.services import products as product_service


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'readiness.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def ready_product(tmp_path, *, price=Decimal("199.90"), name="Produto Pronto", category_slug="jaquetas", image_url="/uploads/products/p/main.jpg"):
    image_path = tmp_path / "main.jpg"
    image_path.write_bytes(b"image")
    brand = Brand(name="Adidas", slug="adidas")
    category = Category(name="Jaquetas", slug=category_slug)
    product = Product(public_id="public-ready", name=name, slug="produto-pronto", price=price, brand=brand, category=category, status="draft", visibility="hidden")
    product.images = [
        ProductImage(filename="main.jpg", storage_path=str(image_path), public_url=image_url, mime_type="image/jpeg", size_bytes=5, width=10, height=10, is_primary=True, position=0)
    ]
    return product


def test_publication_readiness_complete_product_is_eligible(db, tmp_path):
    product = ready_product(tmp_path)

    readiness = product_service.evaluate_publication_readiness(db, product)

    assert readiness["eligible"] is True
    assert readiness["blockers"] == []


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda p: setattr(p, "name", "   "), "PRODUCT_NAME_REQUIRED"),
        (lambda p: setattr(p, "price", Decimal("0.00")), "PRICE_NOT_DEFINED"),
        (lambda p: setattr(p, "price", Decimal("-1.00")), "PRICE_NOT_DEFINED"),
        (lambda p: setattr(p, "brand", None), "BRAND_REQUIRED"),
        (lambda p: setattr(p, "brand", Brand(name="Unknown", slug="unknown")), "BRAND_REQUIRED"),
        (lambda p: setattr(p, "category", None), "CATEGORY_REQUIRED"),
        (lambda p: setattr(p, "category", Category(name="Desconhecidos", slug="desconhecidos")), "CATEGORY_REQUIRED"),
        (lambda p: setattr(p, "images", []), "PRIMARY_IMAGE_REQUIRED"),
        (lambda p: setattr(p.images[0], "is_primary", False), "PRIMARY_IMAGE_REQUIRED"),
        (lambda p: setattr(p.images[0], "public_url", "C:\\local\\image.jpg"), "PRIMARY_IMAGE_REQUIRED"),
    ],
)
def test_publication_readiness_blockers(db, tmp_path, mutate, code):
    product = ready_product(tmp_path)
    mutate(product)

    readiness = product_service.evaluate_publication_readiness(db, product)

    assert code in [blocker["code"] for blocker in readiness["blockers"]]


@pytest.mark.parametrize(
    ("metadata", "code"),
    [
        ({"review": {"needs_name_review": True}}, "NAME_REVIEW_REQUIRED"),
        ({"review": {"brand_conflict": True}}, "BRAND_CONFLICT"),
        ({"unknown_category": True}, "CATEGORY_REVIEW_REQUIRED"),
        ({"import": {"status": "partial"}}, "IMPORT_PARTIAL"),
        ({"import": {"errors": ["failed"]}}, "IMPORT_ERROR"),
        ({"review_required": True}, "REVIEW_REQUIRED"),
    ],
)
def test_publication_readiness_blocks_current_import_review_flags(db, tmp_path, metadata, code):
    product = ready_product(tmp_path)
    db.add(product)
    db.flush()
    record = ImportRecord(source="local_catalog", external_reference="test", status="preview_ready")
    db.add(record)
    db.flush()
    db.add(ImportItem(import_record_id=record.id, external_id="stable", published_product_id=product.id, raw_metadata=metadata, status="published"))
    db.flush()

    readiness = product_service.evaluate_publication_readiness(db, product)

    assert code in [blocker["code"] for blocker in readiness["blockers"]]


def test_publication_readiness_allows_empty_description_and_sizes(db, tmp_path):
    product = ready_product(tmp_path)
    product.description = ""
    product.variants = []

    readiness = product_service.evaluate_publication_readiness(db, product)

    assert readiness["eligible"] is True
    assert readiness["blockers"] == []
    assert {"DESCRIPTION_EMPTY", "SIZES_EMPTY"}.issubset({warning["code"] for warning in readiness["warnings"]})


def test_showcase_readiness_allows_missing_price_with_warning(db, tmp_path):
    product = ready_product(tmp_path, price=Decimal("0.00"))

    showcase = product_service.evaluate_showcase_readiness(db, product)
    commercial = product_service.evaluate_publication_readiness(db, product)

    assert showcase["eligible"] is True
    assert "SHOWCASE_WITHOUT_PRICE" in [warning["code"] for warning in showcase["warnings"]]
    assert "PRICE_NOT_DEFINED" in [blocker["code"] for blocker in commercial["blockers"]]


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda p: setattr(p, "images", []), "PRIMARY_IMAGE_REQUIRED"),
        (lambda p: setattr(p, "category", Category(name="Desconhecidos", slug="desconhecidos")), "CATEGORY_REQUIRED"),
        (lambda p: setattr(p, "brand", Brand(name="Unknown", slug="unknown")), "BRAND_REQUIRED"),
    ],
)
def test_showcase_readiness_blocks_minimum_public_safety(db, tmp_path, mutate, code):
    product = ready_product(tmp_path, price=Decimal("0.00"))
    mutate(product)

    readiness = product_service.evaluate_showcase_readiness(db, product)

    assert readiness["eligible"] is False
    assert code in [blocker["code"] for blocker in readiness["blockers"]]


def test_showcase_readiness_blocks_brand_conflict(db, tmp_path):
    product = ready_product(tmp_path, price=Decimal("0.00"))
    db.add(product)
    db.flush()
    record = ImportRecord(source="local_catalog", external_reference="test", status="preview_ready")
    db.add(record)
    db.flush()
    db.add(ImportItem(import_record_id=record.id, external_id="stable", published_product_id=product.id, raw_metadata={"review": {"brand_conflict": True}}, status="published"))
    db.flush()

    readiness = product_service.evaluate_showcase_readiness(db, product)

    assert readiness["eligible"] is False
    assert "BRAND_CONFLICT" in [blocker["code"] for blocker in readiness["blockers"]]


def test_publication_readiness_returns_multiple_deterministic_blockers(db, tmp_path):
    product = ready_product(tmp_path)
    product.name = " "
    product.price = Decimal("0.00")
    product.brand = None
    product.category = None
    product.images = []

    readiness = product_service.evaluate_publication_readiness(db, product)
    codes = [blocker["code"] for blocker in readiness["blockers"]]

    assert codes == ["PRODUCT_NAME_REQUIRED", "PRICE_NOT_DEFINED", "BRAND_REQUIRED", "CATEGORY_REQUIRED", "PRIMARY_IMAGE_REQUIRED"]
    assert len(codes) == len(set(codes))
