from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ImportItem, ImportRecord
from app.services.import_identity import find_existing_import_item, resolve_import_identity


def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return Session


def add_item(db, *, source, source_type, external_id, url, product_id=None):
    record = ImportRecord(source=source, source_type=source_type, status="preview_ready")
    db.add(record)
    db.flush()
    item = ImportItem(
        import_record_id=record.id,
        external_id=external_id,
        source_url=url,
        normalized_source_url=url,
        status="needs_review",
        published_product_id=product_id,
    )
    db.add(item)
    db.flush()
    return item


def test_same_yupoo_album_with_ignored_query_is_duplicate(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        add_item(
            db,
            source="folder_preview",
            source_type="yupoo",
            external_id="old-hash",
            url="https://deateath.x.yupoo.com/albums/123456?uid=1&referrercate=4572053",
        )
        identity = resolve_import_identity(
            source="folder_preview",
            source_type="yupoo",
            external_id="new-hash",
            source_url="https://deateath.x.yupoo.com/albums/123456?uid=2&isSubCate=false",
        )

        check = find_existing_import_item(db, identity)

        assert check.status == "same_source_existing"


def test_different_yupoo_album_is_new(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        add_item(db, source="folder_preview", source_type="yupoo", external_id="old-hash", url="https://deateath.x.yupoo.com/albums/123456")
        identity = resolve_import_identity(source="folder_preview", source_type="yupoo", external_id="new-hash", source_url="https://deateath.x.yupoo.com/albums/999999")

        check = find_existing_import_item(db, identity)

        assert check.status == "new"


def test_same_fansbuy_supplier_code_same_origin_is_duplicate(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        add_item(db, source="spreadsheet/fansbuy", source_type="spreadsheet", external_id="7792640380", url="https://fansbuy.example/item/7792640380")
        identity = resolve_import_identity(
            source="spreadsheet/fansbuy",
            source_type="spreadsheet",
            external_id="7792640380",
            source_url="https://fansbuy.example/item/7792640380?utm_source=x",
        )

        check = find_existing_import_item(db, identity)

        assert check.status == "same_source_existing"


def test_same_external_id_in_distinct_valid_origins_is_not_automatic_collision(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        add_item(db, source="local_catalog", source_type="local", external_id="ABC123", url="local://catalog/ABC123")
        identity = resolve_import_identity(
            source="spreadsheet/fansbuy",
            source_type="spreadsheet",
            external_id="ABC123",
            source_url="https://fansbuy.example/item/ABC123",
        )

        check = find_existing_import_item(db, identity)

        assert check.status == "new"


def test_external_id_without_url_across_namespaces_requires_manual_review(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        add_item(db, source="local_catalog", source_type="local", external_id="ABC123", url="")
        identity = resolve_import_identity(source="spreadsheet/fansbuy", source_type="spreadsheet", external_id="ABC123")

        check = find_existing_import_item(db, identity)

        assert check.status == "manual_review"
        assert "external_id_reused_across_namespaces" in check.warnings


def test_same_namespace_external_id_with_different_identity_is_conflict(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        add_item(db, source="folder_preview", source_type="folder", external_id="same-hash", url="https://example.com/a")
        identity = resolve_import_identity(source="folder_preview", source_type="folder", external_id="same-hash", source_url="https://example.com/b")

        check = find_existing_import_item(db, identity)

        assert check.status == "conflicting_identity"
        assert "same_namespace_external_id_conflict" in check.warnings


def test_existing_historical_duplicates_do_not_break_identity_lookup(tmp_path):
    Session = session_factory(tmp_path)
    with Session() as db:
        url = "https://deateath.x.yupoo.com/categories/4572053?page=1"
        add_item(db, source="folder_preview", source_type="folder", external_id="cae06bd5eee415731ba03ef1", url=url)
        add_item(db, source="folder_preview", source_type="folder", external_id="cae06bd5eee415731ba03ef1", url=url)
        identity = resolve_import_identity(source="folder_preview", source_type="folder", external_id="cae06bd5eee415731ba03ef1", source_url=url)

        check = find_existing_import_item(db, identity)

        assert check.status == "same_source_existing"
