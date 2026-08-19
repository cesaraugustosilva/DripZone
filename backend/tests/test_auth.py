from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.database import get_db
from app.main import app
from app.models import AdminUser
from app.security import password_hash


def test_login_session_logout_and_csrf(client):
    assert client.get("/api/products").status_code == 401
    invalid = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert invalid.status_code == 401
    inactive = client.post("/api/auth/login", json={"email": "inactive@example.com", "password": "password123"})
    assert inactive.status_code == 401
    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"})
    assert login.status_code == 200
    assert client.get("/api/auth/session").status_code == 200
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    no_csrf = client.post("/api/brands", json={"name": "Nike"})
    assert no_csrf.status_code == 403
    bad_csrf = client.post("/api/brands", json={"name": "Nike"}, headers={"X-CSRF-Token": "bad"})
    assert bad_csrf.status_code == 403
    ok_csrf = client.post("/api/brands", json={"name": "Nike"}, headers={"X-CSRF-Token": csrf})
    assert ok_csrf.status_code == 201
    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 200


def test_tampered_truncated_and_expired_session_cookies_are_rejected(client, monkeypatch):
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 200
    cookie_name = app.state.settings.session_cookie_name
    original_cookie = client.cookies.get(cookie_name)
    assert original_cookie

    client.cookies.set(cookie_name, f"{original_cookie}tampered")
    assert client.get("/api/auth/session").status_code == 401

    client.cookies.set(cookie_name, original_cookie[:20])
    assert client.get("/api/auth/session").status_code == 401

    client.cookies.set(cookie_name, original_cookie)
    monkeypatch.setattr(app.state.settings, "session_max_age", -1)
    assert client.get("/api/auth/session").status_code == 401
    monkeypatch.setattr(app.state.settings, "session_max_age", 28800)


def test_csrf_token_from_another_session_is_rejected(client):
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 200
    owner_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    assert client.post("/api/auth/login", json={"email": "editor@example.com", "password": "password123"}).status_code == 200
    editor_csrf = client.get("/api/auth/csrf").json()["csrf_token"]

    rejected = client.post("/api/brands", json={"name": "Session A"}, headers={"X-CSRF-Token": owner_csrf})
    assert rejected.status_code == 403
    accepted = client.post("/api/brands", json={"name": "Session B"}, headers={"X-CSRF-Token": editor_csrf})
    assert accepted.status_code == 201


def test_password_change_invalidates_existing_sessions(client):
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 200
    csrf_a = client.get("/api/auth/csrf").json()["csrf_token"]

    with TestClient(app) as second_client:
        assert second_client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 200
        assert second_client.get("/api/auth/session").status_code == 200

        change = client.put(
            "/api/users/1",
            json={"name": "Owner", "email": "owner@example.com", "password": "newpass123", "role": "owner", "is_active": True},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert change.status_code == 200
        assert client.get("/api/auth/session").status_code == 401
        assert second_client.get("/api/auth/session").status_code == 401

        assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "newpass123"}).status_code == 200


def test_deactivated_user_cookie_stops_working(client):
    assert client.post("/api/auth/login", json={"email": "editor@example.com", "password": "password123"}).status_code == 200
    assert client.get("/api/auth/session").status_code == 200

    override = app.dependency_overrides[get_db]
    db = next(override())
    try:
        editor = db.query(AdminUser).filter(AdminUser.email == "editor@example.com").one()
        editor.is_active = False
        db.commit()
    finally:
        db.close()

    assert client.get("/api/auth/session").status_code == 401


def test_login_rate_limit_and_pruning(client, monkeypatch):
    now = 1000.0
    monkeypatch.setattr(auth_routes, "time", lambda: now)
    for _ in range(auth_routes.LOGIN_RATE_LIMIT_MAX_FAILURES):
        response = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
        assert response.status_code == 401

    limited = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert limited.status_code == 429

    now += auth_routes.LOGIN_RATE_LIMIT_WINDOW_SECONDS + 1
    allowed = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert allowed.status_code == 401

    auth_routes.attempts["expired"] = [now - auth_routes.LOGIN_RATE_LIMIT_WINDOW_SECONDS - 1]
    auth_routes.prune_attempts(now)
    assert "expired" not in auth_routes.attempts


def test_rate_limit_key_normalizes_email_case(client):
    for _ in range(auth_routes.LOGIN_RATE_LIMIT_MAX_FAILURES):
        response = client.post("/api/auth/login", json={"email": "Owner@Example.com", "password": "wrong"})
        assert response.status_code == 401
    limited = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert limited.status_code == 429
