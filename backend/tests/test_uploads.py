from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.database import get_db
from app.exceptions import ApiError
from app.main import app
from app.models import ProductImage


def image_bytes(fmt="JPEG"):
    data = BytesIO()
    Image.new("RGB", (10, 10), "white").save(data, format=fmt)
    data.seek(0)
    return data


def create_brand_and_category(client, headers, *, slug="upload"):
    brand = client.post("/api/brands", json={"name": f"Brand {slug}", "slug": f"{slug}-brand"}, headers=headers)
    category = client.post("/api/categories", json={"name": f"Category {slug}", "slug": f"{slug}-category"}, headers=headers)
    assert brand.status_code == 201
    assert category.status_code == 201
    return brand.json(), category.json()


def image_storage_path(image_id: int) -> Path:
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        image = db.get(ProductImage, image_id)
        assert image is not None
        return Path(image.storage_path)
    finally:
        db.close()


def test_uploads(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Imagem", "price": "1.00"}, headers=headers).json()
    jpg = client.post(f"/api/products/{product['id']}/images", files={"file": ("a.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    assert jpg.status_code == 201
    png = client.post(f"/api/products/{product['id']}/images", files={"file": ("a.png", image_bytes("PNG"), "image/png")}, headers=headers)
    assert png.status_code == 201
    bad = client.post(f"/api/products/{product['id']}/images", files={"file": ("a.svg", b"<svg></svg>", "image/svg+xml")}, headers=headers)
    assert bad.status_code == 415
    missing = client.post("/api/products/999/images", files={"file": ("a.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    assert missing.status_code == 404


def test_upload_uses_real_image_format_not_original_extension(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Extensao Falsa", "price": "1.00"}, headers=headers).json()

    response = client.post(f"/api/products/{product['id']}/images", files={"file": ("fake.jpg", image_bytes("PNG"), "image/png")}, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["mime_type"] == "image/png"
    assert data["filename"].endswith(".png")


@pytest.mark.parametrize(
    "filename,body,content_type",
    [
        ("text.jpg", BytesIO(b"not an image"), "image/jpeg"),
        ("svg.jpg", BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"), "image/jpeg"),
        ("gif.gif", image_bytes("GIF"), "image/gif"),
        ("mismatch.jpg", image_bytes("PNG"), "image/jpeg"),
    ],
)
def test_upload_rejects_fake_or_unsupported_image_content(authed, filename, body, content_type):
    client, headers = authed
    product = client.post("/api/products", json={"name": f"Produto {filename}", "price": "1.00"}, headers=headers).json()

    response = client.post(f"/api/products/{product['id']}/images", files={"file": (filename, body, content_type)}, headers=headers)

    assert response.status_code == 415


def test_upload_enforces_declared_byte_limit(authed, monkeypatch):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Bytes", "price": "1.00"}, headers=headers).json()
    monkeypatch.setattr("app.api.routes.uploads.settings.max_upload_size", 8)

    response = client.post(f"/api/products/{product['id']}/images", files={"file": ("large.png", image_bytes("PNG"), "image/png")}, headers=headers)

    assert response.status_code == 413


def test_upload_created_file_is_removed_when_public_catalog_stage_fails(authed, tmp_path, monkeypatch):
    client, headers = authed
    brand, category = create_brand_and_category(client, headers, slug="publico")
    product = client.post("/api/products", json={"name": "Produto Publico", "price": "10.00", "brand_id": brand["id"], "category_id": category["id"]}, headers=headers).json()
    image = client.post(f"/api/products/{product['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    assert image.status_code == 201
    assert client.post(f"/api/products/{product['id']}/publish", headers=headers).status_code == 200
    upload_root = Path(app.state.settings.upload_directory)
    before = {path.name for path in upload_root.rglob("*.jpg")}

    def fail_stage(db, path):
        raise RuntimeError("stage failed")

    monkeypatch.setattr("app.api.routes.products.service.stage_public_catalog", fail_stage)

    with pytest.raises(RuntimeError):
        client.post(f"/api/products/{product['id']}/images", files={"file": ("second.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)

    after = {path.name for path in upload_root.rglob("*.jpg")}
    assert after == before
    current = client.get(f"/api/products/{product['id']}").json()
    assert len(current["images"]) == 1


def test_upload_created_file_is_removed_when_db_commit_fails(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Commit Falha", "price": "10.00"}, headers=headers).json()
    upload_root = Path(app.state.settings.upload_directory)
    original_override = app.dependency_overrides[get_db]

    def failing_db():
        gen = original_override()
        db = next(gen)

        def fail_commit():
            raise RuntimeError("commit failed")

        db.commit = fail_commit
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = failing_db
    try:
        with pytest.raises(RuntimeError):
            client.post(f"/api/products/{product['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers)
    finally:
        app.dependency_overrides[get_db] = original_override

    assert list(upload_root.rglob("*.jpg")) == []


def test_delete_image_commits_db_before_removing_file(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Delete Imagem", "price": "10.00"}, headers=headers).json()
    image = client.post(f"/api/products/{product['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers).json()
    storage_path = image_storage_path(image["id"])
    assert storage_path.is_file()

    response = client.delete(f"/api/products/{product['id']}/images/{image['id']}", headers=headers)

    assert response.status_code == 204
    assert not storage_path.exists()
    assert client.get(f"/api/products/{product['id']}").json()["images"] == []


def test_delete_image_filesystem_failure_leaves_db_consistent_and_reports_error(authed, monkeypatch):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Delete Falha", "price": "10.00"}, headers=headers).json()
    image = client.post(f"/api/products/{product['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers).json()

    def fail_remove(storage_path, *, context=None):
        raise ApiError(500, "UPLOAD_DELETE_FAILED", "falha visivel", {"recoverable": True})

    monkeypatch.setattr("app.api.routes.uploads.remove_upload_storage_file", fail_remove)

    response = client.delete(f"/api/products/{product['id']}/images/{image['id']}", headers=headers)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "UPLOAD_DELETE_FAILED"
    assert client.get(f"/api/products/{product['id']}").json()["images"] == []


def test_delete_image_does_not_remove_storage_path_outside_upload_root(authed, tmp_path):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Path Seguro", "price": "10.00"}, headers=headers).json()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(image_bytes("JPEG").getvalue())
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        image = ProductImage(
            product_id=product["id"],
            filename="outside.jpg",
            storage_path=str(outside),
            public_url="/uploads/products/outside.jpg",
            mime_type="image/jpeg",
            size_bytes=outside.stat().st_size,
            width=10,
            height=10,
            is_primary=True,
            position=0,
        )
        db.add(image)
        db.flush()
        image_id = image.id
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    response = client.delete(f"/api/products/{product['id']}/images/{image_id}", headers=headers)

    assert response.status_code == 204
    assert outside.exists()
    assert client.get(f"/api/products/{product['id']}").json()["images"] == []


def test_delete_product_removes_associated_upload_files_after_db_commit(authed):
    client, headers = authed
    product = client.post("/api/products", json={"name": "Produto Delete Arquivos", "price": "10.00"}, headers=headers).json()
    image = client.post(f"/api/products/{product['id']}/images", files={"file": ("main.jpg", image_bytes("JPEG"), "image/jpeg")}, headers=headers).json()
    storage_path = image_storage_path(image["id"])
    assert storage_path.is_file()

    response = client.delete(f"/api/products/{product['id']}", headers=headers)

    assert response.status_code == 204
    assert not storage_path.exists()
    assert client.get(f"/api/products/{product['id']}").status_code == 404
