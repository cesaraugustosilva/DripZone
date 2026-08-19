# DripZone Backup and Restore

This procedure protects the production-like Docker stack prepared in Correction 8. It covers PostgreSQL, uploads, public catalog JSON, and operational metadata needed to prove integrity.

The current validation baseline after the full local catalog sync is 50 administrative products, all in `draft` status and `hidden` visibility, with zero published products in `frontend/data/products.json`. Do not restore to older three-product snapshots unless a separate rollback procedure explicitly calls for that state.

It does not include `.env`, secrets, session keys, tokens, caches, virtual environments, `node_modules`, logs, or Docker volumes themselves.

## Prerequisites

- Docker Desktop running.
- `compose.prod.yaml` available.
- `.env` with PostgreSQL variables.
- `DATABASE_URL` configured or derivable from `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- The main stack running and healthy.

Check:

```powershell
docker compose --env-file .env -f compose.prod.yaml ps
```

## Backup Contents

Each backup is stored outside the active Docker volumes:

```text
backups/
  YYYYMMDD-HHMMSS/
    database.dump
    files.zip
    manifest.json
    checksums.sha256
```

Artifacts:

- `database.dump`: `pg_dump -Fc` custom-format PostgreSQL dump.
- `files.zip`: copy of `/app/storage/uploads` from the backend container and `/app/public-data/products.json`.
- `manifest.json`: metadata without secrets.
- `checksums.sha256`: SHA-256 for the database dump, file archive, and `products.json`.

The manifest includes product totals, status counts, visibility counts, published count, table counts, PostgreSQL version, Alembic version, artifact sizes, hashes, and the current Git commit when available.

## Create a Backup

```powershell
.\scripts\backup-production.ps1
```

Optional:

```powershell
.\scripts\backup-production.ps1 -BackupRoot backups -ComposeFile compose.prod.yaml -EnvFile .env
```

The script fails on the first error, deletes incomplete backup directories, verifies non-empty artifacts, and does not print secrets.

If the PostgreSQL password contains special URL characters such as `@`, `:`, `/`, `#`, or `%`, set `DATABASE_URL` in `.env` using URL encoding.

## Validate Checksums

```powershell
Get-Content backups\YYYYMMDD-HHMMSS\checksums.sha256
Get-FileHash -Algorithm SHA256 backups\YYYYMMDD-HHMMSS\database.dump
Get-FileHash -Algorithm SHA256 backups\YYYYMMDD-HHMMSS\files.zip
```

## Restore in an Isolated Environment

Use this for validation and periodic restore drills:

```powershell
.\scripts\restore-production.ps1 -BackupPath backups\YYYYMMDD-HHMMSS -Isolated
```

The script:

- validates `manifest.json`;
- validates checksums before restoring;
- refuses non-isolated restores unless explicitly allowed;
- starts a temporary PostgreSQL container with its own data;
- restores with `pg_restore`;
- extracts uploads and `products.json` to `backups/_restore-validation`;
- writes validation output to `database-validation.txt`;
- does not alter the main database or main Docker volumes.

Remove temporary containers after validation:

```powershell
docker rm -f dripzone-restore-YYYYMMDD-HHMMSS
```

## Production Restore

Production restore is a maintenance-window operation. Before restoring production:

1. Stop writes and administrative publication/import actions.
2. Create a fresh backup of the current production state.
3. Validate the target backup in an isolated restore.
4. Confirm the intended target, database name, and upload path.
5. Run Alembic only if the application version requires it.
6. Restore PostgreSQL, uploads, and `products.json`.
7. Restart backend/proxy and validate `/api/status`, `/data/products.json`, uploads, admin login, and public catalog.

The provided restore script intentionally refuses non-isolated restore by default. Use `-AllowNonIsolated` only for a planned production procedure with explicit operator confirmation outside this local validation flow.

## Integrity Checks After Restore

For the restored database, compare:

- Alembic version;
- table existence;
- product count;
- product statuses and visibility;
- prices;
- brands and categories;
- product image count;
- import record/item/image counts.

For restored files, compare:

- `products.json` SHA-256;
- upload file count;
- upload file readability;
- expected public paths such as `/uploads/products/...`.

## Retention

Initial policy:

- daily backups: 7 days;
- weekly backups: 4 weeks;
- monthly backups: 3 to 6 months.

At least one encrypted copy should live outside the primary server. A Docker volume is not a backup.

## Security

- `backups/` is ignored by Git.
- `.dockerignore` excludes backups from images.
- Caddy serves only `frontend` and the uploads volume, not `backups/`.
- Do not store `.env` inside a backup.
- Do not paste secrets into tickets, logs, or commit messages.
- Future production hardening should add encrypted off-server copies with keys managed outside the repository.

## Troubleshooting

- `DATABASE_URL` interpolation fails: set it explicitly with URL-encoded password.
- `pg_dump` fails: verify the `postgres` service is healthy.
- `pg_restore` fails: validate `database.dump` checksum and PostgreSQL image compatibility.
- `files.zip` missing: the backup is incomplete and must not be used.
- Checksum mismatch: reject the backup and investigate storage corruption or tampering.
- Restore directory exists: remove the old isolated validation directory or choose a different `-RestoreRoot`.
