import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.imports import preview_import_folder, resolve_brand, validate_source_url


def parse_args():
    parser = argparse.ArgumentParser(description="Cria uma pre-visualizacao de importacao para uma unica pasta.")
    parser.add_argument("--brand", help="Nome ou slug da marca ja cadastrada.")
    parser.add_argument("--brand-id", type=int, help="ID da marca ja cadastrada.")
    parser.add_argument("--url", required=True, help="URL da pasta ou album permitido.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.brand and not args.brand_id:
        print("Informe --brand ou --brand-id.")
        return 2
    with SessionLocal() as db:
        brand = resolve_brand(db, brand_id=args.brand_id, brand=args.brand)
        normalized_url = validate_source_url(args.url)
        print(f"Marca: {brand.name} (ID {brand.id})")
        print(f"Escopo: {normalized_url}")
        print("Somente esta pasta sera analisada. Nenhum produto sera criado.")
        answer = input("Continuar com as requisicoes? [s/N] ").strip().casefold()
        if answer not in {"s", "sim", "y", "yes"}:
            print("Operacao cancelada.")
            return 1
        record = preview_import_folder(db, brand_id=brand.id, brand_name=None, source_url=args.url, user_id=None)
        db.commit()
        print(f"Importacao #{record.id}: {record.status}")
        print(f"Paginas processadas: {record.total_pages or record.current_page}")
        print(f"Itens encontrados: {record.items_found}")
        print(f"Pendentes: {record.items_pending}")
        print(f"Revisao necessaria: {record.items_needs_review}")
        print(f"Revisados: {record.items_reviewed}")
        print(f"Duplicados: {record.duplicate_items}")
        print(f"Imagens selecionadas: {sum(item.image_count for item in record.items)}")
        if record.items:
            print(f"Capa do primeiro item: {record.items[0].cover_image_url or 'nenhuma'}")
        if record.error_message:
            print(f"Aviso: {record.error_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
