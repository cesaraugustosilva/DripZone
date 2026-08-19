import json
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.api.routes import products as product_routes
from app.main import app
from app.models import Brand, Category, Collection, Product, ProductImage, ProductVariant, SneakerModel
from app.services import products as product_service


def image_bytes(fmt="JPEG"):
    data = BytesIO()
    Image.new("RGB", (10, 10), "white").save(data, format=fmt)
    data.seek(0)
    return data


def create_brand_and_category(client, headers, *, brand_slug="adidas", category_slug="jaquetas"):
    brand = client.post("/api/brands", json={"name": brand_slug.title(), "slug": brand_slug}, headers=headers)
    category = client.post("/api/categories", json={"name": category_slug.title(), "slug": category_slug}, headers=headers)
    assert brand.status_code == 201
    assert category.status_code == 201
    return brand.json(), category.json()


def create_eligible_product(client, headers, *, name="Produto Elegivel", slug="produto-elegivel", price="25.00"):
    brand, category = create_brand_and_category(client, headers, brand_slug=f"{slug}-brand", category_slug=f"{slug}-category")
    created = client.post(
        "/api/products",
        json={"name": name, "slug": slug, "price": price, "brand_id": brand["id"], "category_id": category["id"]},
        headers=headers,
    )
    assert created.status_code == 201
    image = client.post(f"/api/products/{created.json()['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    assert image.status_code == 201
    return created.json()


def test_products_crud_publish_filters_and_conflicts(authed):
    client, headers = authed
    empty = client.get("/api/products")
    assert empty.status_code == 200
    assert empty.json()["pagination"]["total"] == 0
    brand, category = create_brand_and_category(client, headers)
    created = client.post("/api/products", json={"name": "Produto Real", "sku": "SKU-1", "price": "10.00", "brand_id": brand["id"], "category_id": category["id"], "status": "draft"}, headers=headers)
    assert created.status_code == 201
    product = created.json()
    duplicate_slug = client.post("/api/products", json={"name": "Outro", "slug": product["slug"], "price": "10.00"}, headers=headers)
    assert duplicate_slug.status_code == 409
    duplicate_sku = client.post("/api/products", json={"name": "Outro", "sku": "SKU-1", "price": "10.00"}, headers=headers)
    assert duplicate_sku.status_code == 409
    got = client.get(f"/api/products/{product['id']}")
    assert got.status_code == 200
    updated = client.patch(f"/api/products/{product['id']}", json={"stock_quantity": 3}, headers=headers)
    assert updated.status_code == 200
    client.post(f"/api/products/{product['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    published = client.post(f"/api/products/{product['id']}/publish", headers=headers)
    assert published.json()["status"] == "published"
    filtered = client.get("/api/products?status=published&sort=name&order=asc")
    assert filtered.json()["pagination"]["total"] == 1
    invalid_sort = client.get("/api/products?sort=password_hash")
    assert invalid_sort.status_code == 400
    unpublished = client.post(f"/api/products/{product['id']}/unpublish", headers=headers)
    assert unpublished.json()["status"] == "draft"
    deleted = client.delete(f"/api/products/{product['id']}", headers=headers)
    assert deleted.status_code == 204


def test_variants_and_export(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Export", "price": "20.00"}, headers=headers).json()
    variant = client.post(f"/api/products/{product['id']}/variants", json={"size": "M", "stock_quantity": 2}, headers=headers)
    assert variant.status_code == 201
    export_empty = client.post("/api/products/export", headers=headers)
    assert export_empty.status_code == 200
    assert export_empty.json()["products"] == []


def test_public_product_serializer_contract_for_complete_product():
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    product = Product(public_id="public-1", name="Adidas Jacket", slug="adidas-jacket", price=Decimal("199.90"), description="Produto completo.", created_at=created_at)
    product.brand = Brand(name="Adidas", slug="adidas")
    product.category = Category(name="Jaquetas", slug="jaquetas")
    product.sneaker_model = SneakerModel(name="Campus 00", slug="campus-00")
    product.collections = [
        Collection(name="Inverno", slug="inverno", position=2),
        Collection(name="Drop Principal", slug="drop-principal", position=1),
    ]
    product.images = [
        ProductImage(filename="side.jpg", storage_path="C:\\local\\side.jpg", public_url="/uploads/products/public-1/side.jpg", mime_type="image/jpeg", size_bytes=100, width=10, height=10, is_primary=False, position=1),
        ProductImage(filename="main.jpg", storage_path="C:\\local\\main.jpg", public_url="/uploads/products/public-1/main.jpg", mime_type="image/jpeg", size_bytes=100, width=10, height=10, is_primary=True, position=0),
        ProductImage(filename="bad.jpg", storage_path="C:\\local\\bad.jpg", public_url="C:\\local\\bad.jpg", mime_type="image/jpeg", size_bytes=100, width=10, height=10, is_primary=False, position=2),
    ]
    product.variants = [
        ProductVariant(size="M", stock_quantity=2, is_active=True, position=0),
        ProductVariant(size="G", stock_quantity=2, is_active=True, position=1),
        ProductVariant(size="G", stock_quantity=2, is_active=True, position=2),
        ProductVariant(size="P", stock_quantity=2, is_active=False, position=3),
    ]

    data = product_service.serialize_public_product(product)

    assert data["id"] == "adidas-jacket"
    assert data["slug"] == "adidas-jacket"
    assert data["name"] == "Adidas Jacket"
    assert data["price"] == 199.9
    assert isinstance(data["price"], float)
    assert data["purchasable"] is True
    assert data["availability"] == "available"
    assert data["image"] == "/uploads/products/public-1/main.jpg"
    assert data["gallery"] == ["/uploads/products/public-1/main.jpg", "/uploads/products/public-1/side.jpg"]
    assert all("\\" not in image and ":" not in image for image in data["gallery"])
    assert data["category"] == "Jaquetas"
    assert data["categoryId"] == "jaquetas"
    assert data["brand"] == "Adidas"
    assert data["brandId"] == "adidas"
    assert data["modelId"] == "campus-00"
    assert data["collectionId"] == "drop-principal"
    assert data["collectionIds"] == ["drop-principal", "inverno"]
    assert data["sizes"] == ["M", "G"]
    assert data["description"] == "Produto completo."
    assert data["createdAt"] == "2026-01-02T03:04:05+00:00"
    datetime.fromisoformat(data["createdAt"])


def test_public_product_serializer_handles_missing_public_values():
    created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    product = Product(public_id="public-2", name="Produto Sem Preco", slug="produto-sem-preco", price=Decimal("0.00"), description=None, created_at=created_at)
    product.images = [
        ProductImage(filename="bad.jpg", storage_path="C:\\local\\bad.jpg", public_url="C:\\local\\bad.jpg", mime_type="image/jpeg", size_bytes=100, width=10, height=10, is_primary=True, position=0)
    ]
    product.variants = []

    data = product_service.serialize_public_product(product)

    assert data["id"] == "produto-sem-preco"
    assert data["price"] is None
    assert data["purchasable"] is False
    assert data["availability"] == "coming_soon"
    assert data["image"] is None
    assert data["gallery"] == []
    assert data["category"] == ""
    assert data["categoryId"] == ""
    assert data["brand"] == ""
    assert data["brandId"] == ""
    assert data["modelId"] == ""
    assert data["collectionId"] == ""
    assert data["collectionIds"] == []
    assert data["sizes"] == []
    assert isinstance(data["sizes"], list)
    assert data["description"] == ""
    assert isinstance(data["description"], str)
    assert datetime.fromisoformat(data["createdAt"]) == created_at


def test_public_product_serializer_hides_supplier_links_from_description():
    product = Product(public_id="public-link", name="Produto Link", slug="produto-link", price=Decimal("0.00"), description="https://item.taobao.com/item.htm?id=123")

    data = product_service.serialize_public_product(product)

    assert data["description"] == "Produto em vitrine temporária. Detalhes comerciais em revisão."
    assert "taobao" not in data["description"].lower()


def test_public_export_uses_serializer_and_writes_products_root(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'export.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    calls = []

    with TestingSessionLocal() as db:
        product = Product(public_id="public-3", name="Produto Exportavel", slug="produto-exportavel", price=Decimal("50.00"), status="published", visibility="public")
        db.add(product)
        db.commit()

        def fake_serializer(item):
            calls.append(item.slug)
            return {"id": item.slug, "slug": item.slug, "name": item.name, "price": 50.0}

        monkeypatch.setattr(product_service, "serialize_public_product", fake_serializer)
        output_path = tmp_path / "products.json"
        data = product_service.export_public_products(db, output_path)

    assert calls == ["produto-exportavel"]
    assert "products" in data
    assert data["products"] == [{"id": "produto-exportavel", "slug": "produto-exportavel", "name": "Produto Exportavel", "price": 50.0}]
    assert json.loads(output_path.read_text(encoding="utf-8")) == data


def test_public_export_uses_status_as_canonical_publication_field(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add_all([
            Product(public_id="public-4", name="Published Hidden", slug="published-hidden", price=Decimal("10.00"), status="published", visibility="hidden"),
            Product(public_id="public-5", name="Draft Public", slug="draft-public", price=Decimal("10.00"), status="draft", visibility="public"),
        ])
        db.commit()
        data = product_service.export_public_products(db, tmp_path / "products.json")

    assert [product["id"] for product in data["products"]] == ["published-hidden"]


def test_public_export_atomic_write_keeps_previous_file_on_replace_failure(tmp_path, monkeypatch):
    output_path = tmp_path / "products.json"
    previous = {"version": 1, "updatedAt": None, "products": [{"id": "old"}]}
    output_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(product_service.os, "replace", fail_replace)

    with pytest.raises(OSError):
        product_service.write_json_atomically(output_path, {"version": 1, "updatedAt": None, "products": [{"id": "new"}]})

    assert json.loads(output_path.read_text(encoding="utf-8")) == previous
    assert list(tmp_path.glob(".products.json.*.tmp")) == []


def test_public_export_order_is_deterministic(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'order.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add_all([
            Product(public_id="public-6", name="Produto B", slug="produto-b", price=Decimal("10.00"), status="published", visibility="public"),
            Product(public_id="public-7", name="Produto A", slug="produto-a", price=Decimal("10.00"), status="published", visibility="public"),
        ])
        db.commit()
        first = product_service.export_public_products(db, tmp_path / "products.json")
        second = product_service.export_public_products(db, tmp_path / "products.json")

    assert [product["id"] for product in first["products"]] == ["produto-a", "produto-b"]
    assert first == second


def test_public_export_has_unique_ids_and_slugs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unique.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add_all([
            Product(public_id="public-8", name="Produto A", slug="produto-a", price=Decimal("0.00"), status="published", visibility="public"),
            Product(public_id="public-9", name="Produto B", slug="produto-b", price=Decimal("0.00"), status="published", visibility="public"),
        ])
        db.commit()
        data = product_service.export_public_products(db, tmp_path / "products.json")

    ids = [product["id"] for product in data["products"]]
    slugs = [product["slug"] for product in data["products"]]
    assert len(ids) == len(set(ids))
    assert len(slugs) == len(set(slugs))


def test_exported_product_contract_is_consumable_by_public_catalog_and_product_page(authed):
    client, headers = authed
    brand = client.post("/api/brands", json={"name": "Adidas", "slug": "adidas"}, headers=headers)
    category = client.post("/api/categories", json={"name": "Jaquetas", "slug": "jaquetas"}, headers=headers)
    assert brand.status_code == 201
    assert category.status_code == 201
    product = client.post(
        "/api/products",
        json={
            "name": "Adidas Jacket",
            "slug": "adidas-jacket",
            "price": "250.00",
            "description": "Jaqueta Adidas.",
            "brand_id": brand.json()["id"],
            "category_id": category.json()["id"],
            "status": "draft",
        },
        headers=headers,
    )
    assert product.status_code == 201
    variant = client.post(f"/api/products/{product.json()['id']}/variants", json={"size": "M", "stock_quantity": 2}, headers=headers)
    image = client.post(f"/api/products/{product.json()['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    assert variant.status_code == 201
    assert image.status_code == 201
    published = client.post(f"/api/products/{product.json()['id']}/publish", headers=headers)
    assert published.status_code == 200

    exported = client.post("/api/products/export", headers=headers)
    assert exported.status_code == 200
    data = exported.json()
    item = data["products"][0]

    assert set(["id", "slug", "name", "price", "image", "gallery", "category", "categoryId", "brand", "brandId", "sizes", "description", "createdAt"]).issubset(item)
    assert item["id"] == item["slug"] == "adidas-jacket"
    assert isinstance(item["price"], float)
    assert item["image"] == item["gallery"][0]
    assert item["gallery"] == [image.json()["public_url"]]
    assert item["category"] == "Jaquetas"
    assert item["categoryId"] == "jaquetas"
    assert item["brand"] == "Adidas"
    assert item["brandId"] == "adidas"
    assert item["sizes"] == ["M"]
    assert item["description"] == "Jaqueta Adidas."
    datetime.fromisoformat(item["createdAt"])


def test_publish_and_unpublish_regenerate_public_catalog(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    product = create_eligible_product(client, headers, name="Produto Publicavel", slug="produto-publicavel", price="30.00")
    assert product["visibility"] == "hidden"
    assert not output_path.exists()

    published = client.post(f"/api/products/{product['id']}/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["visibility"] == "public"
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"][0]["id"] == "produto-publicavel"

    unpublished = client.post(f"/api/products/{product['id']}/unpublish", headers=headers)
    assert unpublished.status_code == 200
    assert unpublished.json()["status"] == "draft"
    assert unpublished.json()["visibility"] == "hidden"
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"] == []


def test_public_variant_changes_regenerate_public_catalog(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    product = create_eligible_product(client, headers, name="Produto Variantes Publicas", slug="produto-variantes-publicas", price="120.00")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200

    variant = client.post(f"/api/products/{product['id']}/variants", json={"size": "42", "stock_quantity": 2}, headers=headers)
    assert variant.status_code == 201
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["products"][0]["sizes"] == ["42"]

    updated = client.put(f"/api/products/{product['id']}/variants/{variant.json()['id']}", json={"size": "43", "stock_quantity": 2}, headers=headers)
    assert updated.status_code == 200
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["products"][0]["sizes"] == ["43"]

    deleted = client.delete(f"/api/products/{product['id']}/variants/{variant.json()['id']}", headers=headers)
    assert deleted.status_code == 204
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["products"][0]["sizes"] == []


def test_public_image_changes_regenerate_public_catalog(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    product = create_eligible_product(client, headers, name="Produto Imagens Publicas", slug="produto-imagens-publicas", price="140.00")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200

    second = client.post(f"/api/products/{product['id']}/images", files={"file": ("second.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    assert second.status_code == 201
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert second.json()["public_url"] in data["products"][0]["gallery"]

    primary = client.post(f"/api/products/{product['id']}/images/{second.json()['id']}/primary", headers=headers)
    assert primary.status_code == 200
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["products"][0]["image"] == second.json()["public_url"]


def test_draft_variant_and_image_changes_do_not_touch_public_catalog(authed, tmp_path):
    client, headers = authed
    output_path = tmp_path / "products.json"
    output_path.write_text(json.dumps({"version": 1, "updatedAt": None, "products": [{"id": "published"}]}), encoding="utf-8")
    product = create_eligible_product(client, headers, name="Produto Draft Catalogo", slug="produto-draft-catalogo", price="120.00")

    variant = client.post(f"/api/products/{product['id']}/variants", json={"size": "40", "stock_quantity": 2}, headers=headers)
    current = client.get(f"/api/products/{product['id']}").json()
    image_id = current["images"][0]["id"]
    image_update = client.put(f"/api/products/{product['id']}/images/{image_id}?position=3", headers=headers)

    assert variant.status_code == 201
    assert image_update.status_code == 200
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"] == [{"id": "published"}]


def test_create_update_patch_and_delete_regenerate_catalog_when_public_state_changes(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    created = create_eligible_product(client, headers, name="Produto Direto", slug="produto-direto", price="40.00")
    published = client.post(f"/api/products/{created['id']}/publish", headers=headers)
    assert published.status_code == 200
    assert [item["id"] for item in json.loads(output_path.read_text(encoding="utf-8"))["products"]] == ["produto-direto"]

    updated = client.put(
        f"/api/products/{created['id']}",
        json={"name": "Produto Direto Editado", "slug": "produto-direto", "price": "40.00", "brand_id": created["brand_id"], "category_id": created["category_id"], "status": "draft", "visibility": "public"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["visibility"] == "hidden"
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"] == []

    patched = client.patch(f"/api/products/{created['id']}", json={"status": "published", "visibility": "hidden"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["visibility"] == "public"
    assert [item["id"] for item in json.loads(output_path.read_text(encoding="utf-8"))["products"]] == ["produto-direto"]

    deleted = client.delete(f"/api/products/{created['id']}", headers=headers)
    assert deleted.status_code == 204
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"] == []


def test_publish_and_unpublish_are_idempotent(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"

    product = create_eligible_product(client, headers, name="Produto Idempotente", slug="produto-idempotente", price="20.00")

    first_publish = client.post(f"/api/products/{product['id']}/publish", headers=headers)
    second_publish = client.post(f"/api/products/{product['id']}/publish", headers=headers)
    assert first_publish.status_code == 200
    assert second_publish.status_code == 200
    assert second_publish.json()["status"] == "published"
    published_products = json.loads(output_path.read_text(encoding="utf-8"))["products"]
    assert [item["id"] for item in published_products] == ["produto-idempotente"]

    first_unpublish = client.post(f"/api/products/{product['id']}/unpublish", headers=headers)
    second_unpublish = client.post(f"/api/products/{product['id']}/unpublish", headers=headers)
    assert first_unpublish.status_code == 200
    assert second_unpublish.status_code == 200
    assert second_unpublish.json()["status"] == "draft"
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"] == []


def test_publish_and_unpublish_missing_product_return_404(authed):
    client, headers = authed

    publish = client.post("/api/products/999/publish", headers=headers)
    unpublish = client.post("/api/products/999/unpublish", headers=headers)

    assert publish.status_code == 404
    assert publish.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert unpublish.status_code == 404
    assert unpublish.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_publication_endpoints_require_authentication_and_csrf(client):
    assert client.post("/api/products/1/publish").status_code == 401
    assert client.post("/api/products/1/unpublish").status_code == 401
    assert client.post("/api/products/export").status_code == 401

    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"})
    assert login.status_code == 200
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    product = create_eligible_product(client, headers, name="Produto Seguro", slug="produto-seguro", price="15.00")
    assert client.post(f"/api/products/{product['id']}/publish").status_code == 403
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200
    assert client.post(f"/api/products/{product['id']}/unpublish", headers=headers).status_code == 200
    assert client.post("/api/products/export", headers=headers).status_code == 200


def test_publication_export_failure_rolls_back_product_state(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    previous = {"version": 1, "updatedAt": None, "products": [{"id": "old"}]}
    output_path.write_text(json.dumps(previous), encoding="utf-8")
    product = create_eligible_product(client, headers, name="Produto Rollback", slug="produto-rollback", price="22.00")

    def fail_stage(db, path):
        raise RuntimeError("stage failed")

    monkeypatch.setattr(product_routes.service, "stage_public_catalog", fail_stage)

    with pytest.raises(RuntimeError):
        client.post(f"/api/products/{product['id']}/publish", headers=headers)

    current = client.get(f"/api/products/{product['id']}").json()
    assert current["status"] == "draft"
    assert current["visibility"] == "hidden"
    assert json.loads(output_path.read_text(encoding="utf-8")) == previous


def test_unpublication_export_failure_rolls_back_product_state(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    product = create_eligible_product(client, headers, name="Produto Rollback Publicado", slug="produto-rollback-publicado", price="22.00")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200

    def fail_stage(db, path):
        raise RuntimeError("stage failed")

    monkeypatch.setattr(product_routes.service, "stage_public_catalog", fail_stage)

    with pytest.raises(RuntimeError):
        client.post(f"/api/products/{product['id']}/unpublish", headers=headers)

    current = client.get(f"/api/products/{product['id']}").json()
    assert current["status"] == "published"
    assert current["visibility"] == "public"


def test_public_catalog_publish_failure_after_db_commit_is_recoverable(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    output_path.write_text(json.dumps({"version": 1, "updatedAt": None, "products": [{"id": "old"}]}), encoding="utf-8")
    product = create_eligible_product(client, headers, name="Produto Commitado", slug="produto-commitado", price="44.00")

    def fail_publish(stage):
        raise OSError("replace failed")

    monkeypatch.setattr(product_routes.service, "publish_public_catalog_stage", fail_publish)

    response = client.post(f"/api/products/{product['id']}/publish", headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PUBLIC_CATALOG_PUBLISH_FAILED"
    current = client.get(f"/api/products/{product['id']}").json()
    assert current["status"] == "published"
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"] == [{"id": "old"}]

    monkeypatch.setattr(product_routes.service, "publish_public_catalog_stage", product_service.publish_public_catalog_stage)
    repaired = client.post("/api/products/export", headers=headers)
    assert repaired.status_code == 200
    assert json.loads(output_path.read_text(encoding="utf-8"))["products"][0]["id"] == "produto-commitado"


def test_publication_readiness_endpoint_returns_blockers(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Incompleto", "slug": "produto-incompleto", "price": "0.00"}, headers=headers).json()

    response = client.get(f"/api/products/{product['id']}/publication-readiness")

    assert response.status_code == 200
    data = response.json()
    assert data["eligible"] is False
    assert {"PRICE_NOT_DEFINED", "BRAND_REQUIRED", "CATEGORY_REQUIRED", "PRIMARY_IMAGE_REQUIRED"}.issubset({blocker["code"] for blocker in data["blockers"]})


def test_publish_incomplete_product_returns_all_blockers_without_export_or_status_change(authed, monkeypatch):
    client, headers = authed
    export_calls = []
    monkeypatch.setattr(product_routes.service, "stage_public_catalog", lambda db, path: export_calls.append(path))
    product = client.post("/api/products", json={"name": "Produto Bloqueado", "slug": "produto-bloqueado", "price": "0.00"}, headers=headers).json()

    response = client.post(f"/api/products/{product['id']}/publish", headers=headers)

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "PRODUCT_NOT_READY_FOR_PUBLICATION"
    assert {"PRICE_NOT_DEFINED", "BRAND_REQUIRED", "CATEGORY_REQUIRED", "PRIMARY_IMAGE_REQUIRED"} == {blocker["code"] for blocker in body["details"]["blockers"]}
    assert client.get(f"/api/products/{product['id']}").json()["status"] == "draft"
    assert export_calls == []


def test_create_update_and_patch_to_published_require_readiness(authed):
    client, headers = authed

    created = client.post("/api/products", json={"name": "Produto Criado Publicado", "slug": "produto-criado-publicado", "price": "0.00", "status": "published"}, headers=headers)
    assert created.status_code == 422
    assert created.json()["error"]["code"] == "PRODUCT_NOT_READY_FOR_PUBLICATION"

    draft = client.post("/api/products", json={"name": "Produto Draft", "slug": "produto-draft", "price": "0.00"}, headers=headers).json()
    updated = client.put(f"/api/products/{draft['id']}", json={"name": "Produto Draft", "slug": "produto-draft", "price": "0.00", "status": "published"}, headers=headers)
    patched = client.patch(f"/api/products/{draft['id']}", json={"status": "published"}, headers=headers)
    assert updated.status_code == 422
    assert patched.status_code == 422
    assert client.get(f"/api/products/{draft['id']}").json()["status"] == "draft"


def test_published_product_cannot_be_updated_to_invalid_state(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    original_export = product_service.export_public_products
    monkeypatch.setattr(product_routes.service, "export_public_products", lambda db, path: original_export(db, output_path))
    product = create_eligible_product(client, headers, name="Produto Publicado Valido", slug="produto-publicado-valido", price="299.90")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200

    zero_price = client.patch(f"/api/products/{product['id']}", json={"price": "0.00"}, headers=headers)
    assert zero_price.status_code == 422
    current = client.get(f"/api/products/{product['id']}").json()
    assert current["status"] == "published"
    assert current["price"] == "299.90"

    zero_price_put = client.put(
        f"/api/products/{product['id']}",
        json={"name": current["name"], "slug": current["slug"], "price": "0.00", "brand_id": current["brand_id"], "category_id": current["category_id"], "status": "published"},
        headers=headers,
    )
    assert zero_price_put.status_code == 422
    current = client.get(f"/api/products/{product['id']}").json()
    assert current["price"] == "299.90"

    valid_change = client.patch(f"/api/products/{product['id']}", json={"stock_quantity": 5}, headers=headers)
    assert valid_change.status_code == 200
    assert valid_change.json()["status"] == "published"


def test_deleting_primary_image_from_published_product_is_rejected(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    original_export = product_service.export_public_products
    monkeypatch.setattr(product_routes.service, "export_public_products", lambda db, path: original_export(db, output_path))
    product = create_eligible_product(client, headers, name="Produto Com Imagem", slug="produto-com-imagem", price="100.00")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200
    current = client.get(f"/api/products/{product['id']}").json()
    image_id = current["images"][0]["id"]

    response = client.delete(f"/api/products/{product['id']}/images/{image_id}", headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["details"]["blockers"][0]["code"] == "PRIMARY_IMAGE_REQUIRED"
    assert len(client.get(f"/api/products/{product['id']}").json()["images"]) == 1


def test_setting_invalid_primary_image_on_published_product_is_rejected(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    original_export = product_service.export_public_products
    monkeypatch.setattr(product_routes.service, "export_public_products", lambda db, path: original_export(db, output_path))
    product = create_eligible_product(client, headers, name="Produto Primary Invalida", slug="produto-primary-invalida", price="100.00")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        bad_image = ProductImage(
            product_id=product["id"],
            filename="bad.jpg",
            storage_path=str(tmp_path / "missing.jpg"),
            public_url="C:\\missing\\bad.jpg",
            mime_type="image/jpeg",
            size_bytes=10,
            width=10,
            height=10,
            alt_text=None,
            is_primary=False,
            position=1,
        )
        db.add(bad_image)
        db.flush()
        bad_image_id = bad_image.id
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    response = client.post(f"/api/products/{product['id']}/images/{bad_image_id}/primary", headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["details"]["blockers"][0]["code"] == "PRIMARY_IMAGE_REQUIRED"
    current = client.get(f"/api/products/{product['id']}").json()
    primary_images = [image for image in current["images"] if image["is_primary"]]
    assert len(primary_images) == 1
    assert primary_images[0]["id"] != bad_image_id


def test_unpublish_then_save_incomplete_draft_is_allowed(authed, tmp_path, monkeypatch):
    client, headers = authed
    output_path = tmp_path / "products.json"
    original_export = product_service.export_public_products
    monkeypatch.setattr(product_routes.service, "export_public_products", lambda db, path: original_export(db, output_path))
    product = create_eligible_product(client, headers, name="Produto Para Despublicar", slug="produto-para-despublicar", price="80.00")
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200
    assert client.post(f"/api/products/{product['id']}/unpublish", headers=headers).status_code == 200

    draft_update = client.patch(f"/api/products/{product['id']}", json={"price": "0.00"}, headers=headers)
    publish_again = client.post(f"/api/products/{product['id']}/publish", headers=headers)

    assert draft_update.status_code == 200
    assert draft_update.json()["status"] == "draft"
    assert publish_again.status_code == 422
    assert publish_again.json()["error"]["details"]["blockers"][0]["code"] == "PRICE_NOT_DEFINED"
