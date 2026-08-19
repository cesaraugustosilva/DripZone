from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.database import SessionLocal
from app.services.spreadsheet_pilot_apply import EXPECTED_RUN_ID, apply_spreadsheet_pilot


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aplica o piloto validado da planilha DripZone ao banco.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir)
    with SessionLocal() as db:
        result = apply_spreadsheet_pilot(db, run_dir, dry_run=args.dry_run)
    payload = result.as_dict()
    payload["expected_run_id"] = EXPECTED_RUN_ID
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
