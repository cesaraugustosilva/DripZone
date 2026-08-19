import argparse

from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import ImportImage, ImportItem
from app.services.import_image_ingestion import evaluate_ingestion_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica prontidao de ingestao de uma imagem do importador.")
    parser.add_argument("--import-id", type=int, required=True)
    parser.add_argument("--item-id", type=int, required=True)
    parser.add_argument("--image-id", type=int, required=True)
    args = parser.parse_args()

    with SessionLocal() as db:
        image = (
            db.query(ImportImage)
            .options(selectinload(ImportImage.import_item).selectinload(ImportItem.import_record))
            .join(ImportItem, ImportImage.import_item_id == ImportItem.id)
            .filter(ImportItem.import_record_id == args.import_id, ImportItem.id == args.item_id, ImportImage.id == args.image_id)
            .first()
        )
        if not image:
            print("IMPORT_IMAGE_NOT_FOUND")
            return 1
        readiness = evaluate_ingestion_readiness(image)
        print(readiness)
        return 0 if readiness["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
