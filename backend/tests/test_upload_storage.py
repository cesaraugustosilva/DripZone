import pytest

from app.exceptions import ApiError
from app.services import upload_storage
from app.utils.files import ensure_child_path


def test_docker_canonical_upload_directory_allows_postgres(monkeypatch):
    monkeypatch.setattr(upload_storage.settings, "database_url", "postgresql+psycopg://dripzone:secret@postgres:5432/dripzone")
    monkeypatch.setattr(upload_storage.settings, "upload_directory", "/app/storage/uploads")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    upload_storage.ensure_canonical_upload_write_allowed()


def test_host_upload_directory_blocks_postgres_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(upload_storage.settings, "database_url", "postgresql+psycopg://dripzone:secret@postgres:5432/dripzone")
    monkeypatch.setattr(upload_storage.settings, "upload_directory", str(tmp_path / "uploads"))
    monkeypatch.delenv(upload_storage.ALLOW_HOST_UPLOAD_WRITES_ENV, raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(ApiError) as exc:
        upload_storage.ensure_canonical_upload_write_allowed()

    assert exc.value.code == "UPLOAD_STORAGE_NOT_CANONICAL"


def test_sqlite_tmp_upload_directory_is_allowed_for_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(upload_storage.settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(upload_storage.settings, "upload_directory", str(tmp_path / "uploads"))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    upload_storage.ensure_canonical_upload_write_allowed()


def test_upload_public_url_contract_stays_relative():
    public_id = "public-id"
    filename = "image.jpg"

    assert f"/uploads/products/{public_id}/{filename}" == "/uploads/products/public-id/image.jpg"
    assert ":\\" not in f"/uploads/products/{public_id}/{filename}"


@pytest.mark.parametrize("candidate_name", ["../outside.jpg", "..\\outside.jpg"])
def test_upload_write_path_rejects_traversal(candidate_name, tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()

    with pytest.raises(ValueError):
        ensure_child_path(root, root / candidate_name)


def test_upload_delete_path_rejects_absolute_external_path(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    outside = tmp_path / "outside.jpg"
    root.mkdir()
    outside.write_bytes(b"outside")
    monkeypatch.setattr(upload_storage.settings, "upload_directory", str(root))

    assert upload_storage.remove_upload_storage_file(outside) is False
    assert outside.exists()
