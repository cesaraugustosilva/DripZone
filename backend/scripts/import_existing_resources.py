import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import AccessoryType, Brand, Category, Collection, SneakerModel
from app.utils.slug import unique_slug

ROOT = Path(__file__).resolve().parents[2]


def read_items(path: Path, keys: list[str]) -> list:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in keys:
        if isinstance(data.get(key), list):
            return data[key]
    return []


def item_name(item) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("name") or item.get("title") or item.get("label")
    return None


def upsert(db, model, name: str, dry_run: bool) -> bool:
    if db.query(model).filter(model.name == name).first():
        return False
    if not dry_run:
        db.add(model(name=name, slug=unique_slug(db, model, name), is_active=True, position=0))
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    frontend_data = ROOT / "frontend" / "data"
    sources = [
        ("brands", Brand, frontend_data / "brands.json", ["brands", "items"]),
        ("categories", Category, frontend_data / "categories.json", ["categories", "items"]),
        ("collections", Collection, frontend_data / "collections.json", ["collections", "items"]),
        ("accessories", AccessoryType, frontend_data / "accessories.json", ["accessories", "items"]),
        ("sneakers", SneakerModel, frontend_data / "sneakers.json", ["sneakers", "models", "items"]),
    ]
    summary = {}
    with SessionLocal() as db:
        for label, model, path, keys in sources:
            created = 0
            skipped = 0
            for item in read_items(path, keys):
                name = item_name(item)
                if not name:
                    skipped += 1
                    continue
                created += 1 if upsert(db, model, name, args.dry_run) else 0
            summary[label] = {"would_create" if args.dry_run else "created": created, "skipped": skipped}
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
