from app.models import Brand, Category
from scripts.sync_catalog_resources import build_report, load_catalog_resources, normalize_key


def test_catalog_resources_are_loaded_from_public_json():
    resources = load_catalog_resources()
    brand_names = {item.name for item in resources["brands"]}
    category_names = {item.name for item in resources["categories"]}
    assert "Syna World" in brand_names
    assert "Synaworld" not in brand_names
    assert "Camisetas" in category_names


def test_normalization_prevents_syna_world_duplicate():
    assert normalize_key(" Syna   World ") == normalize_key("syna-world")
    assert normalize_key("Synaworld") != normalize_key("Syna World")


def test_dry_run_report_is_idempotent_and_preserves_database(client):
    from app.database import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    try:
      db.add(Brand(name="Syna World", slug="syna-world", is_active=True, position=0))
      db.add(Category(name="Camisetas", slug="camisetas", is_active=True, position=0))
      db.commit()
      before = (db.query(Brand).count(), db.query(Category).count())
      first = build_report(db)
      second = build_report(db)
      after = (db.query(Brand).count(), db.query(Category).count())
    finally:
      db.close()
    assert before == after
    assert first["summary"] == second["summary"]
    assert any(row["catalog_value"] == "Syna World" and row["action"] == "exists" for row in first["brands"])
    assert any(row["catalog_value"] == "Camisetas" and row["action"] == "exists" for row in first["categories"])


def test_slug_conflict_is_reported_without_create(client):
    from app.database import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    try:
      db.add(Brand(name="Different Name", slug="nike", is_active=True, position=0))
      db.commit()
      report = build_report(db)
    finally:
      db.close()
    nike = next(row for row in report["brands"] if row["catalog_value"] == "Nike")
    assert nike["action"] == "skip_conflict"
    assert nike["possible_duplicate"]
