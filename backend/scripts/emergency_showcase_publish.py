import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[2] if (SCRIPT_PATH.parents[2] / "backend").exists() else SCRIPT_PATH.parents[1]
BACKEND_ROOT = ROOT / "backend" if (ROOT / "backend").exists() else ROOT
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Category, Product, utc_now
from app.services.products import (
    evaluate_showcase_readiness,
    export_public_products,
    product_query,
    write_bytes_atomically,
)


SHOWCASE_CORRECTIONS = {
    212: {"name": "Adidas Polo Manga Longa", "category_slug": "camisetas"},
    213: {"name": "Adidas Camiseta Manga Longa", "category_slug": "camisetas"},
    217: {
        "name": "Adidas Camiseta Real Madrid",
        "category_slug": "camisetas",
        "primary_filename": "01-962a11d67ad8b893.jpg",
    },
}


def public_products_path() -> Path:
    return Path(os.environ.get("PUBLIC_PRODUCTS_PATH") or ROOT / "frontend" / "data" / "products.json")


def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if value:
        return value
    return "sqlite:///./storage/database/dripzone.db"


def issue_codes(items):
    return [item["code"] for item in items]


def apply_corrections(db, product):
    correction = SHOWCASE_CORRECTIONS.get(product.id)
    if not correction:
        return []

    changes = []
    if correction.get("name") and product.name != correction["name"]:
        changes.append({"field": "name", "before": product.name, "after": correction["name"]})
        product.name = correction["name"]

    category_slug = correction.get("category_slug")
    if category_slug:
        category = db.query(Category).filter(Category.slug == category_slug).one()
        before = product.category.slug if product.category else None
        if before != category_slug:
            changes.append({"field": "category", "before": before, "after": category_slug})
            product.category = category

    primary_filename = correction.get("primary_filename")
    if primary_filename:
        target = next((image for image in product.images if image.filename == primary_filename), None)
        if target and not target.is_primary:
            current = next((image for image in product.images if image.is_primary), None)
            changes.append({"field": "primary_image", "before": current.filename if current else None, "after": target.filename})
            for image in product.images:
                image.is_primary = image.id == target.id
            target.position = 0

    return changes


def build_plan(db, *, with_corrections: bool):
    products = db.execute(product_query().order_by(Product.id.asc())).scalars().all()
    apt = []
    blocked = []
    adjustments = []
    for product in products:
        if with_corrections:
            changes = apply_corrections(db, product)
            if changes:
                adjustments.append({"id": product.id, "slug": product.slug, "changes": changes})
        readiness = evaluate_showcase_readiness(db, product)
        entry = {
            "id": product.id,
            "slug": product.slug,
            "name": product.name,
            "brand": product.brand.slug if product.brand else None,
            "category": product.category.slug if product.category else None,
            "image_count": len(product.images or []),
            "price": str(product.price),
            "blockers": issue_codes(readiness["blockers"]),
            "warnings": issue_codes(readiness["warnings"]),
        }
        if readiness["eligible"]:
            apt.append(entry)
        else:
            blocked.append(entry)
    return {"apt": apt, "blocked": blocked, "adjustments": adjustments}


def validate_unique_public_ids(data):
    ids = [item["id"] for item in data["products"]]
    slugs = [item["slug"] for item in data["products"]]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Public catalog has duplicate ids.")
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("Public catalog has duplicate slugs.")


def apply_showcase(db, output_path: Path):
    previous_content = output_path.read_bytes() if output_path.exists() else None
    previous_existed = output_path.exists()
    try:
        plan = build_plan(db, with_corrections=True)
        now = utc_now()
        for item in plan["apt"]:
            product = db.get(Product, item["id"])
            product.status = "published"
            product.visibility = "public"
            product.availability = "coming_soon"
            product.published_at = product.published_at or now
        db.flush()
        data = export_public_products(db, output_path)
        validate_unique_public_ids(data)
        if any(product["price"] is not None or product["purchasable"] for product in data["products"]):
            raise RuntimeError("Showcase export unexpectedly contains purchasable or priced products.")
        db.commit()
        return plan, data
    except Exception:
        db.rollback()
        if previous_existed and previous_content is not None:
            write_bytes_atomically(output_path, previous_content)
        elif output_path.exists():
            output_path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    engine = create_engine(database_url(), future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    output_path = Path(args.output) if args.output else public_products_path()

    with SessionLocal() as db:
        if args.apply:
            plan, data = apply_showcase(db, output_path)
            result = {"mode": "apply", **plan, "exported": len(data["products"])}
        else:
            plan = build_plan(db, with_corrections=True)
            db.rollback()
            result = {"mode": "dry-run", **plan, "exported": 0}

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
