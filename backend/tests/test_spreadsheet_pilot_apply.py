from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Brand, Category, ImportItem, Product
from app.services import spreadsheet_pilot_apply as apply_mod


def make_image(path: Path) -> dict:
    Image.new("RGB", (20, 20), "white").save(path, format="PNG")
    digest = apply_mod.file_sha256(path)
    return {
        "source_type": "embedded_xlsx",
        "filename": path.name,
        "status": "stored",
        "position": 1,
        "mime": "image/png",
        "size_bytes": path.stat().st_size,
        "sha256": digest,
        "width": 20,
        "height": 20,
    }


def proposal(run_dir: Path, *, code: str, name: str, brand: str, category_slug: str = "moletons", category_name: str = "Moletons", row: int = 1) -> dict:
    image_path = run_dir / "images" / f"{code}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = make_image(image_path)
    return {
        "spreadsheet_row": row,
        "supplier_code": code,
        "supplier_url": f"https://fansbuy.com/item-micro-{code}.html?promotionCode=59125a2689826be5",
        "hyperlink_source": "fansbuy_formula_derived",
        "supplier_name": name,
        "suggested_name": name,
        "detected_brand": brand,
        "brand_id": None,
        "brand_status": "would_create",
        "category_id": None,
        "category_slug": category_slug,
        "category_name": category_name,
        "spreadsheet_category": f"{category_slug} original",
        "price_usd_reference": "$26",
        "price_brl_reference": "R$136",
        "commercial_price": None,
        "supplier_page": {"status": "ok"},
        "supplier_images": [image],
        "warnings": [],
        "_proposal_relative_path": f"products/{row}-{code}.json",
    }


def make_run(tmp_path: Path, proposals: list[dict]) -> Path:
    run_dir = tmp_path / apply_mod.EXPECTED_RUN_ID
    (run_dir / "products").mkdir(parents=True, exist_ok=True)
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": apply_mod.EXPECTED_RUN_ID,
        "products_count": 10,
        "workbook_sha256": "abc",
        "proposals": [item["_proposal_relative_path"] for item in proposals],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for item in proposals:
        payload = dict(item)
        relative = payload.pop("_proposal_relative_path")
        source_image = tmp_path / "images" / payload["supplier_images"][0]["filename"]
        target_image = run_dir / "images" / payload["supplier_images"][0]["filename"]
        if source_image.exists() and source_image != target_image:
            target_image.write_bytes(source_image.read_bytes())
        (run_dir / relative).write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


@pytest.fixture()
def pilot_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'apply.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(apply_mod.settings, "upload_directory", str(tmp_path / "uploads"))
    with Session() as db:
        db.add(Brand(name="Adidas", slug="adidas", is_active=True))
        db.add(Brand(name="Jordan", slug="jordan", is_active=True))
        db.add(Category(name="Moletons", slug="moletons", is_active=True))
        db.add(Category(name="Sneakers", slug="sneakers", is_active=True))
        db.commit()
    return Session


def base_proposals(run_dir: Path) -> list[dict]:
    return [
        proposal(run_dir, code="7792640380", name="Air Jordan 4", brand="Jordan", category_slug="sneakers", category_name="Sneakers", row=10),
        proposal(run_dir, code="7789591169", name="Adidas Hoodie", brand="Adidas", row=194),
        proposal(run_dir, code="7792669908", name="Adwysd Hoodie", brand="Adwysd", row=195),
        proposal(run_dir, code="7789575461", name="Camisas Ami", brand="Ami", category_slug="moletons", category_name="Moletons", row=118),
    ]


def patch_allowed_codes(monkeypatch):
    monkeypatch.setattr(
        apply_mod,
        "PRODUCT_NAMES",
        {
            "7792640380": "Air Jordan 4",
            "7789591169": "Adidas Hoodie",
            "7792669908": "Adwysd Hoodie",
        },
    )
    monkeypatch.setattr(apply_mod, "BLOCKED_CODES", {"7789575461": "ambiguous_brand_manual_review"})


def test_applies_products_brands_images_traceability_and_idempotency(tmp_path, monkeypatch, pilot_session):
    patch_allowed_codes(monkeypatch)
    proposals = base_proposals(tmp_path)
    run_dir = make_run(tmp_path, proposals)
    with pilot_session() as db:
        result = apply_mod.apply_spreadsheet_pilot(db, run_dir)
        second = apply_mod.apply_spreadsheet_pilot(db, run_dir)
        assert result.products_created == 3
        assert second.products_created == 0
        assert second.products_existing == 3
        assert db.query(Brand).filter(Brand.slug == "adwysd").one().is_active is True
        assert db.query(Product).filter(Product.sku == "7789575461").first() is None
        product = db.query(Product).filter(Product.sku == "7792669908").one()
        assert product.status == "draft"
        assert product.visibility == "hidden"
        assert product.price == Decimal("0.00")
        assert product.images[0].public_url.startswith("/uploads/products/")
        assert "imports/pilots" not in product.images[0].public_url
        assert Path(product.images[0].storage_path).is_file()
        item = db.query(ImportItem).filter(ImportItem.external_id == "7792669908").one()
        assert item.raw_metadata["supplier"]["price_brl_reference"] == "R$136"
        assert item.raw_metadata["run"]["proposal"] == "products/195-7792669908.json"
        assert item.published_product_id == product.id


def test_existing_brand_is_reused_and_ambiguous_brand_is_blocked(tmp_path, monkeypatch, pilot_session):
    patch_allowed_codes(monkeypatch)
    run_dir = make_run(tmp_path, base_proposals(tmp_path))
    with pilot_session() as db:
        result = apply_mod.apply_spreadsheet_pilot(db, run_dir)
        assert {"name": "Adidas", "id": db.query(Brand).filter(Brand.slug == "adidas").one().id} in result.brands_existing
        assert result.blocked[0]["supplier_code"] == "7789575461"
        assert db.query(Brand).filter(Brand.slug == "ami").first() is None


def test_item_rollback_keeps_other_items_atomic(tmp_path, monkeypatch, pilot_session):
    patch_allowed_codes(monkeypatch)
    proposals = base_proposals(tmp_path)
    run_dir = make_run(tmp_path, proposals)
    bad_image = run_dir / "images" / "7792669908.png"
    bad_image.unlink()
    with pilot_session() as db:
        result = apply_mod.apply_spreadsheet_pilot(db, run_dir)
        assert any(item["supplier_code"] == "7792669908" for item in result.failed)
        assert db.query(Product).filter(Product.sku == "7792669908").first() is None
        assert db.query(Product).filter(Product.sku == "7792640380").one()
        assert db.query(Product).filter(Product.sku == "7789591169").one()


def test_dry_run_rolls_back_everything(tmp_path, monkeypatch, pilot_session):
    patch_allowed_codes(monkeypatch)
    run_dir = make_run(tmp_path, base_proposals(tmp_path))
    with pilot_session() as db:
        result = apply_mod.apply_spreadsheet_pilot(db, run_dir, dry_run=True)
        assert result.products_created == 3
        assert db.query(Product).count() == 0
        assert db.query(Brand).filter(Brand.slug == "adwysd").first() is None
        assert not Path(apply_mod.settings.upload_directory).exists()
