from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Brand, Category, ImportItem, ImportRecord, Product
from app.services import product_enrichment as enrichment
from app.services.spreadsheet_pilot import load_spreadsheet_products


def make_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'enrichment.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with Session() as db:
        for name, slug in [
            ("Adidas", "adidas"),
            ("Jordan", "jordan"),
            ("Nike", "nike"),
            ("Balenciaga", "balenciaga"),
            ("Corteiz", "corteiz"),
            ("Givenchy", "givenchy"),
        ]:
            db.add(Brand(name=name, slug=slug, is_active=True))
        for name, slug in [
            ("Sneakers", "sneakers"),
            ("Camisetas", "camisetas"),
            ("Moletons", "moletons"),
            ("Calças", "calcas"),
            ("Conjuntos", "conjuntos"),
            ("Jaquetas", "jaquetas"),
            ("Acessórios", "acessorios"),
        ]:
            db.add(Category(name=name, slug=slug, is_active=True))
        db.commit()
    return Session


def make_image(path: Path) -> dict:
    Image.new("RGB", (30, 30), "black").save(path, format="PNG")
    digest = enrichment.file_sha256(path)
    return {
        "source_type": "embedded_xlsx",
        "filename": path.name,
        "status": "stored",
        "position": 1,
        "mime": "image/png",
        "size_bytes": path.stat().st_size,
        "sha256": digest,
        "width": 30,
        "height": 30,
    }


def proposal(run_dir: Path, *, code: str, name: str, brand: str, category_slug: str, category_name: str, decision: str, row: int = 10, warnings=None) -> dict:
    image_path = run_dir / "images" / f"{code}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = make_image(image_path)
    return {
        "spreadsheet_row": row,
        "supplier_code": code,
        "supplier_url": f"https://fansbuy.com/item-micro-{code}.html?promotionCode=59125a2689826be5",
        "supplier_name": name,
        "suggested_name": name,
        "detected_brand": brand,
        "category_slug": category_slug,
        "category_name": category_name,
        "spreadsheet_category": category_slug,
        "price_usd_reference": "$99",
        "price_brl_reference": "R$500",
        "supplier_images": [image],
        "warnings": [],
        "enrichment": {
            "supplier_code": code,
            "supplier_name": name,
            "detected_brand": brand,
            "official_name": enrichment.commercial_name(
                type("P", (), {"supplier_name": name, "category_slug": category_slug})(),
                brand,
            )[0],
            "official_model": None,
            "style_code": None,
            "variant": None,
            "category_id": None,
            "name_confidence": 0.9,
            "brand_confidence": 0.98,
            "category_confidence": 0.95,
            "image_match_confidence": 0.9,
            "warnings": warnings or [],
            "decision": decision,
            "research": [{"status": "skipped"}],
        },
        "_proposal_relative_path": f"products/{row}-{code}.json",
    }


def make_run(tmp_path: Path, proposals: list[dict]) -> Path:
    run_dir = tmp_path / "enriched-test-limit25"
    (run_dir / "products").mkdir(parents=True, exist_ok=True)
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_dir.name,
        "products_count": 25,
        "workbook_sha256": "abc",
        "proposals": [item["_proposal_relative_path"] for item in proposals],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for item in proposals:
        relative = item["_proposal_relative_path"]
        payload = dict(item)
        payload.pop("_proposal_relative_path")
        source_image = tmp_path / "images" / payload["supplier_images"][0]["filename"]
        target_image = run_dir / "images" / payload["supplier_images"][0]["filename"]
        if source_image.exists() and source_image != target_image:
            target_image.write_bytes(source_image.read_bytes())
        (run_dir / relative).write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


def test_name_rules_keep_price_and_batch_out_and_translate_types():
    product = type("P", (), {"supplier_name": "Adidas Samba [PK BATCH]\n(Várias cores)", "category_slug": "sneakers"})()
    assert enrichment.commercial_name(product, "Adidas")[0] == "Adidas Samba"
    hoodie = type("P", (), {"supplier_name": "Balenciaga Zipper Hoodie", "category_slug": "moletons"})()
    assert enrichment.commercial_name(hoodie, "Balenciaga")[0] == "Moletom Balenciaga com Ziper"
    jeans = type("P", (), {"supplier_name": "Corteiz Jeans", "category_slug": "calcas"})()
    assert enrichment.commercial_name(jeans, "Corteiz")[0] == "Calca Jeans Corteiz"
    bag = type("P", (), {"supplier_name": "Nike Backpack", "category_slug": "acessorios"})()
    assert enrichment.commercial_name(bag, "Nike")[0] == "Mochila Nike"


def test_enrichment_decisions_cover_confidence_duplicate_multiple_variant_and_blocked(tmp_path):
    Session = make_db(tmp_path)
    with Session() as db:
        db.add(Product(public_id="p-existing", name="Existing", slug="existing", sku="111", price=0))
        db.commit()
        selected = [
            type("P", (), {"supplier_code": "222", "supplier_name": "Balenciaga Hoodie", "category_slug": "moletons", "supplier_url": "https://fansbuy.com/item-micro-222.html"})(),
            type("P", (), {"supplier_code": "333", "supplier_name": "Adidas Samba\n(Várias cores)", "category_slug": "sneakers", "supplier_url": "https://fansbuy.com/item-micro-333.html"})(),
            type("P", (), {"supplier_code": "111", "supplier_name": "Nike Pants", "category_slug": "calcas", "supplier_url": "https://fansbuy.com/item-micro-111.html"})(),
            type("P", (), {"supplier_code": "444", "supplier_name": "Ami Shirt", "category_slug": "camisetas", "supplier_url": "https://fansbuy.com/item-micro-444.html"})(),
        ]
        base = {"supplier_images": [{"status": "stored"}], "warnings": [], "category_name": "Moletons"}
        auto = enrichment.enrich_proposal(db, {**base, "supplier_code": "222", "supplier_name": "Balenciaga Hoodie", "detected_brand": "Balenciaga", "category_slug": "moletons", "supplier_url": selected[0].supplier_url}, selected)
        multi = enrichment.enrich_proposal(db, {**base, "supplier_code": "333", "supplier_name": selected[1].supplier_name, "detected_brand": "Adidas", "category_slug": "sneakers", "supplier_url": selected[1].supplier_url}, selected)
        dup = enrichment.enrich_proposal(db, {**base, "supplier_code": "111", "supplier_name": "Nike Pants", "detected_brand": "Nike", "category_slug": "calcas", "supplier_url": selected[2].supplier_url}, selected)
        ambiguous = enrichment.enrich_proposal(db, {**base, "supplier_code": "444", "supplier_name": "Ami Shirt", "detected_brand": "Ami", "category_slug": "camisetas", "supplier_url": selected[3].supplier_url}, selected)
        assert auto.decision == "auto_apply"
        assert multi.decision == "manual_review"
        assert "multiple_variants_source" in multi.warnings
        assert dup.decision == "blocked"
        assert ambiguous.decision == "blocked"


def test_apply_publishes_auto_apply_showcase_keeps_manual_draft_and_is_idempotent(tmp_path, monkeypatch):
    Session = make_db(tmp_path)
    monkeypatch.setattr(enrichment.settings, "upload_directory", str(tmp_path / "uploads"))
    proposals = [
        proposal(tmp_path, code="9001", name="Balenciaga Hoodie", brand="Balenciaga", category_slug="moletons", category_name="Moletons", decision="auto_apply", row=1),
        proposal(tmp_path, code="9002", name="Adidas Samba\n(Várias cores)", brand="Adidas", category_slug="sneakers", category_name="Sneakers", decision="manual_review", row=2, warnings=["multiple_variants_source"]),
        proposal(tmp_path, code="9003", name="Ami Shirt", brand="Ami", category_slug="camisetas", category_name="Camisetas", decision="blocked", row=3, warnings=["brand_requires_manual_review"]),
    ]
    filler = [
        proposal(tmp_path, code=str(9100 + index), name="Givenchy Set", brand="Givenchy", category_slug="conjuntos", category_name="Conjuntos", decision="manual_review", row=10 + index)
        for index in range(22)
    ]
    run_dir = make_run(tmp_path, proposals + filler)
    output = tmp_path / "products.json"
    with Session() as db:
        first = enrichment.apply_enriched_batch(db, run_dir, output_path=output)
        second = enrichment.apply_enriched_batch(db, run_dir, output_path=output)
        assert first.products_created == 24
        assert second.products_created == 0
        published = db.query(Product).filter(Product.sku == "9001").one()
        manual = db.query(Product).filter(Product.sku == "9002").one()
        assert published.status == "published"
        assert published.price == 0
        assert manual.status == "draft"
        assert manual.visibility == "hidden"
        assert db.query(Product).filter(Product.sku == "9003").first() is None
        public_data = json.loads(output.read_text(encoding="utf-8"))
        item = next(product for product in public_data["products"] if product["slug"] == published.slug)
        assert item["price"] is None
        assert item["purchasable"] is False
        assert item["availability"] == "coming_soon"


def test_dry_run_rolls_back_database_and_public_json(tmp_path, monkeypatch):
    Session = make_db(tmp_path)
    monkeypatch.setattr(enrichment.settings, "upload_directory", str(tmp_path / "uploads"))
    proposals = [
        proposal(tmp_path, code=str(9200 + index), name="Balenciaga Hoodie", brand="Balenciaga", category_slug="moletons", category_name="Moletons", decision="auto_apply", row=index)
        for index in range(25)
    ]
    run_dir = make_run(tmp_path, proposals)
    output = tmp_path / "products.json"
    output.write_text('{"version":1,"products":[]}', encoding="utf-8")
    before = output.read_text(encoding="utf-8")
    with Session() as db:
        result = enrichment.apply_enriched_batch(db, run_dir, dry_run=True, output_path=output)
        assert result.products_created == 25
        assert db.query(Product).count() == 0
        assert output.read_text(encoding="utf-8") == before
