import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Brand, Category, Product
from app.utils.slug import make_slug

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DATA = ROOT / "frontend" / "data"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class CatalogResource:
    kind: str
    name: str
    slug: str
    active: bool
    aliases: tuple[str, ...]
    source: str
    product_count: int = 0

    @property
    def normalized(self) -> str:
        return normalize_key(self.name)


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", repair_text(str(value or ""))).strip()


def repair_text(value: str) -> str:
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value


def normalize_key(value: str | None) -> str:
    cleaned = normalize_space(value).casefold()
    decomposed = unicodedata.normalize("NFKD", cleaned)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_only).strip()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_catalog_resources(frontend_data: Path = FRONTEND_DATA) -> dict[str, list[CatalogResource]]:
    products = read_json(frontend_data / "products.json").get("products", [])
    brands = resource_items(frontend_data / "brands.json", "brands", "brand", products)
    categories = resource_items(frontend_data / "categories.json", "all", "category", products)
    return {"brands": brands, "categories": categories}


def resource_items(path: Path, key: str, kind: str, products: list[dict]) -> list[CatalogResource]:
    data = read_json(path)
    explicit_items = data.get(key, [])
    product_values = values_from_products(products, kind)
    items = [resource_from_mapping(kind, item, path.name) for item in explicit_items if isinstance(item, dict)]
    explicit_keys = {item.normalized for item in items}
    for value, count in sorted(product_values.items()):
        if normalize_key(value) in explicit_keys:
            continue
        items.append(CatalogResource(kind=kind, name=value, slug=make_slug(value), active=True, aliases=(), source="products.json", product_count=count))
    return dedupe_catalog_items(items)


def values_from_products(products: list[dict], kind: str) -> Counter:
    fields = ("brand", "brandName", "brand_id", "brandId") if kind == "brand" else ("category", "categoryName", "category_id", "categoryId")
    values: Counter = Counter()
    for product in products:
        for field in fields:
            value = normalize_space(product.get(field))
            if value:
                values[value] += 1
                break
    return values


def resource_from_mapping(kind: str, item: dict, source: str) -> CatalogResource:
    name = normalize_space(item.get("name") or item.get("title") or item.get("label"))
    slug = normalize_space(item.get("slug")) or make_slug(name)
    aliases = tuple(normalize_space(alias) for alias in item.get("aliases", []) if normalize_space(alias))
    return CatalogResource(kind=kind, name=name, slug=make_slug(slug), active=item.get("active", item.get("is_active", True)) is not False, aliases=aliases, source=source)


def dedupe_catalog_items(items: Iterable[CatalogResource]) -> list[CatalogResource]:
    by_key: dict[str, CatalogResource] = {}
    for item in items:
        if not item.name:
            continue
        key = item.normalized
        if key not in by_key:
            by_key[key] = item
    return list(by_key.values())


def aliases_for(item: CatalogResource) -> set[str]:
    values = {item.name, *item.aliases}
    return {normalize_key(value) for value in values if normalize_key(value)}


def audit_resource(db, model, item: CatalogResource) -> dict:
    existing = db.query(model).all()
    product_field = Product.brand_id if model is Brand else Product.category_id
    matched = None
    conflicts = []
    item_aliases = aliases_for(item)

    for record in existing:
        record_keys = {normalize_key(record.name)}
        if item_aliases & record_keys:
            matched = record
            break

    slug_owner = next((record for record in existing if record.slug == item.slug), None)
    if slug_owner and (not matched or slug_owner.id != matched.id):
        conflicts.append(f"slug_conflict:{slug_owner.id}:{slug_owner.name}")

    name_owner = next((record for record in existing if normalize_key(record.name) == item.normalized), None)
    if name_owner and (not matched or name_owner.id != matched.id):
        conflicts.append(f"name_conflict:{name_owner.id}:{name_owner.name}")

    ambiguous_aliases = []
    for record in existing:
        if matched and record.id == matched.id:
            continue
        if aliases_for(item) & {normalize_key(record.name)}:
            ambiguous_aliases.append(f"{record.id}:{record.name}")
    if ambiguous_aliases:
        conflicts.append(f"alias_conflict:{','.join(ambiguous_aliases)}")

    product_count = db.query(Product).filter(product_field == matched.id).count() if matched else 0
    action = "skip_conflict" if conflicts else "exists" if matched else "create"
    return {
        "catalog_value": item.name,
        "normalized": item.normalized,
        "proposed_slug": item.slug,
        "exists": bool(matched),
        "existing_id": matched.id if matched else None,
        "existing_status": matched.is_active if matched else None,
        "product_count": product_count,
        "possible_duplicate": conflicts,
        "action": action,
        "source": item.source,
    }


def build_report(db) -> dict:
    catalog = load_catalog_resources()
    brands = [audit_resource(db, Brand, item) for item in catalog["brands"]]
    categories = [audit_resource(db, Category, item) for item in catalog["categories"]]
    return {
        "source": {
            "brands": str((FRONTEND_DATA / "brands.json").relative_to(ROOT)),
            "categories": str((FRONTEND_DATA / "categories.json").relative_to(ROOT)),
            "products": str((FRONTEND_DATA / "products.json").relative_to(ROOT)),
        },
        "database": {
            "brands": db.query(Brand).count(),
            "categories": db.query(Category).count(),
            "products": db.query(Product).count(),
        },
        "brands": brands,
        "categories": categories,
        "summary": {
            "brands_found": len(brands),
            "brands_existing": sum(1 for item in brands if item["action"] == "exists"),
            "brands_would_create": sum(1 for item in brands if item["action"] == "create"),
            "brands_conflicts": sum(1 for item in brands if item["action"] == "skip_conflict"),
            "categories_found": len(categories),
            "categories_existing": sum(1 for item in categories if item["action"] == "exists"),
            "categories_would_create": sum(1 for item in categories if item["action"] == "create"),
            "categories_conflicts": sum(1 for item in categories if item["action"] == "skip_conflict"),
        },
    }


def apply_report(db, report: dict) -> None:
    for row in report["brands"]:
        if row["action"] == "create":
            db.add(Brand(name=row["catalog_value"], slug=row["proposed_slug"], is_active=True, position=0))
    for row in report["categories"]:
        if row["action"] == "create":
            db.add(Category(name=row["catalog_value"], slug=row["proposed_slug"], is_active=True, position=0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync public catalog brands and categories into admin database.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Only report changes. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Create missing non-conflicting resources.")
    args = parser.parse_args()

    with SessionLocal() as db:
        report = build_report(db)
        report["mode"] = "apply" if args.apply else "dry-run"
        if args.apply:
            apply_report(db, report)
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
