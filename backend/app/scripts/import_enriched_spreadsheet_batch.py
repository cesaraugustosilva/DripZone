from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.database import SessionLocal
from app.services.product_enrichment import (
    apply_enriched_batch,
    generate_enriched_batch,
    manifest_summary,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa lote enriquecido da planilha DripZone.")
    parser.add_argument("--xlsx", default="/app/imports/source/dripzone-piloto-mais-vendidos.xlsx")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output-root", default="/app/imports/enriched")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload: dict
    with SessionLocal() as db:
        if args.run_dir:
            run_dir = Path(args.run_dir)
            result = apply_enriched_batch(db, run_dir, dry_run=not args.apply)
            payload = {"mode": "apply" if args.apply else "apply_dry_run", "result": result.as_dict(), "summary": manifest_summary(run_dir)}
        else:
            manifest = generate_enriched_batch(
                db,
                xlsx=Path(args.xlsx),
                limit=args.limit,
                output_root=Path(args.output_root),
            )
            payload = {
                "mode": "dry_run",
                "manifest": manifest,
                "run_dir": str(Path(args.output_root) / manifest["run_id"]),
                "summary": manifest_summary(Path(args.output_root) / manifest["run_id"]),
            }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.verbose else None))
    result = payload.get("result") or {}
    return 1 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
