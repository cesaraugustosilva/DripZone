import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AdminUser
from app.security import password_hash, validate_auth_email, validate_password_strength, verify_password
from scripts.reset_admin_password import get_admin_by_email, reset_admin_password


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin-password.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with Session() as session:
        yield session


@pytest.fixture()
def admin(db):
    user = AdminUser(
        name="Administrador DripZone",
        email="admin@dripzone.com.br",
        password_hash=password_hash("OldStrong#123"),
        role="owner",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_validate_auth_email_matches_api_expectations():
    assert validate_auth_email(" ADMIN@DRIPZONE.COM.BR ") == "admin@dripzone.com.br"
    with pytest.raises(ValueError, match="E-mail invalido."):
        validate_auth_email("admin@dripzone.local")


def test_password_rules_reject_weak_mismatch_identity_and_current(admin):
    with pytest.raises(ValueError, match="12 caracteres"):
        validate_password_strength("Aa1!", "Aa1!")
    with pytest.raises(ValueError, match="nao conferem"):
        validate_password_strength("NewStrong#123", "Different#123")
    with pytest.raises(ValueError, match="igual ao e-mail"):
        validate_password_strength("admin@dripzone.com.br", "admin@dripzone.com.br", email=admin.email)
    with pytest.raises(ValueError, match="igual ao nome"):
        validate_password_strength("Administrador DripZone", "Administrador DripZone", name=admin.name)
    with pytest.raises(ValueError, match="senha atual"):
        validate_password_strength("OldStrong#123", "OldStrong#123", current_hash=admin.password_hash)


def test_reset_rejects_missing_email_and_cancel(db, admin):
    with pytest.raises(ValueError, match="nao encontrado"):
        get_admin_by_email(db, "missing@dripzone.com.br")
    old_hash = admin.password_hash
    old_updated_at = admin.updated_at
    with pytest.raises(ValueError, match="cancelada"):
        reset_admin_password(
            db,
            email=admin.email,
            password="NewStrong#123",
            confirmation="NewStrong#123",
            confirmed=False,
        )
    db.rollback()
    db.refresh(admin)
    assert admin.password_hash == old_hash
    assert admin.updated_at == old_updated_at


def test_reset_updates_only_hash_and_updated_at(db, admin):
    old_hash = admin.password_hash
    old_created_at = admin.created_at
    old_last_login_at = admin.last_login_at
    old_session_version = admin.session_version
    reset_admin_password(
        db,
        email=admin.email,
        password="NewStrong#123",
        confirmation="NewStrong#123",
        confirmed=True,
    )
    db.commit()
    db.refresh(admin)
    assert admin.id == 1
    assert admin.name == "Administrador DripZone"
    assert admin.email == "admin@dripzone.com.br"
    assert admin.role == "owner"
    assert admin.is_active is True
    assert admin.created_at == old_created_at
    assert admin.last_login_at == old_last_login_at
    assert admin.session_version == old_session_version + 1
    assert admin.updated_at != old_created_at
    assert admin.password_hash != old_hash
    assert admin.password_hash != "NewStrong#123"
    assert verify_password("NewStrong#123", admin.password_hash)
    assert not verify_password("WrongStrong#123", admin.password_hash)
