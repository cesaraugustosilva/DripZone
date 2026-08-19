import argparse
import json
import sys
from pathlib import Path

from app.database import SessionLocal
from app.services.local_catalog_sync import LocalCatalogSyncOptions, sync_local_catalog


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Sincroniza backend/catalog com o banco administrativo em rascunho.")
    parser.add_argument("--catalog-root", default="catalog", help="Diretorio raiz do catalogo local.")
    parser.add_argument("--dry-run", action="store_true", help="Valida e resume sem persistir banco ou arquivos.")
    parser.add_argument("--limit", type=int, default=None, help="Quantidade maxima de produtos a processar.")
    parser.add_argument("--product-id", default=None, help="ID/source_id especifico do product.json.")
    parser.add_argument("--category", default=None, help="Slug da categoria local a processar.")
    parser.add_argument("--verbose", action="store_true", help="Inclui detalhes por produto no resumo.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    options = LocalCatalogSyncOptions(
        catalog_root=Path(args.catalog_root),
        dry_run=args.dry_run,
        limit=args.limit,
        product_id=args.product_id,
        category=args.category,
        verbose=args.verbose,
    )
    try:
        with SessionLocal() as db:
            result = sync_local_catalog(db, options)
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 1 if result.failed else 0
    except Exception as exc:
        print(json.dumps({"fatal": True, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
