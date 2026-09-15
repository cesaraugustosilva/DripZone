import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.services.sneaker_taxonomy import SNEAKER_MENU_TAXONOMY, seed_sneaker_menu_taxonomy


def main() -> None:
    with SessionLocal() as db:
        summary = seed_sneaker_menu_taxonomy(db)
        db.commit()

    summary["models"] = [
        {"brand": item.brand_name, "name": item.name, "slug": item.slug}
        for item in SNEAKER_MENU_TAXONOMY
    ]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
