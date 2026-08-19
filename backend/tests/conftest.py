import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import AdminUser
from app.security import password_hash
from app.api.routes.auth import attempts
from app.api.routes import products as product_routes


@pytest.fixture()
def client(tmp_path, monkeypatch):
    attempts.clear()
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = TestingSessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(product_routes.settings, "public_products_path", str(tmp_path / "products.json"))
    app.dependency_overrides[get_db] = override_db
    app.state.settings.upload_directory = str(upload_dir)
    with TestingSessionLocal() as db:
        db.add(AdminUser(name="Owner", email="owner@example.com", password_hash=password_hash("password123"), role="owner", is_active=True))
        db.add(AdminUser(name="Editor", email="editor@example.com", password_hash=password_hash("password123"), role="editor", is_active=True))
        db.add(AdminUser(name="Inactive", email="inactive@example.com", password_hash=password_hash("password123"), role="owner", is_active=False))
        db.commit()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def authed(client):
    response = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"})
    assert response.status_code == 200
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    return client, {"X-CSRF-Token": csrf}


@pytest.fixture()
def editor(client):
    response = client.post("/api/auth/login", json={"email": "editor@example.com", "password": "password123"})
    assert response.status_code == 200
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    return client, {"X-CSRF-Token": csrf}
