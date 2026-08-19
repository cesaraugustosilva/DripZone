# DripZone Production Operations

This guide prepares a local production-like run. It does not deploy to an external server, configure DNS, or issue a real certificate.

## Architecture

Browser -> Caddy reverse proxy -> static frontend/admin, `/uploads`, `/data/products.json`, and `/api` -> FastAPI backend -> PostgreSQL.

Caddy was chosen because it keeps the stack small, serves static files, reverse-proxies the API, adds security headers, compresses responses, and can obtain HTTPS certificates automatically once a real domain points to the server.

## Required Files

- `compose.prod.yaml`: production-like compose stack.
- `backend/Dockerfile`: FastAPI production image.
- `deploy/caddy/Caddyfile`: local HTTP proxy configuration.
- `deploy/caddy/Caddyfile.https.example`: production HTTPS example with HSTS.
- `.env`: local secrets and production values, ignored by Git.

## Environment

Copy `.env.example` to `.env` and replace every placeholder secret.

Required for `compose.prod.yaml`:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `SESSION_SECRET_KEY`
- `CORS_ORIGINS`
- `DRIPZONE_SITE_ADDRESS`
- `HTTP_PORT`
- `HTTPS_PORT`

Production rules:

- `APP_ENV` is set to `production` by compose.
- `APP_DEBUG` is set to `false`.
- `DATABASE_URL` points to the internal `postgres` service.
- If the database password contains special URL characters such as `@`, `:`, `/`, `#`, or `%`, encode it in `DATABASE_URL`.
- `CORS_ORIGINS` must list real origins only, for example `https://dripzone.com.br`.
- `SESSION_SECRET_KEY` must be unique and at least 32 characters.
- Localhost origins are development-only.

## Start Development

```powershell
.\scripts\start-development.ps1
```

Frontend: `http://127.0.0.1:4173/`

Backend API: `http://127.0.0.1:3000/api`

## Start Production-Like Stack

```powershell
docker compose --env-file .env -f compose.prod.yaml up -d --build
```

Local proxy:

- Frontend/admin: `http://127.0.0.1:8080/`
- Admin login: `http://127.0.0.1:8080/admin/login/`
- API via proxy: `http://127.0.0.1:8080/api/status`
- Public catalog JSON: `http://127.0.0.1:8080/data/products.json`
- Uploads: `http://127.0.0.1:8080/uploads/...`

PostgreSQL is not published to the host by `compose.prod.yaml`; only backend reaches it on the internal Docker network.

The compose startup order is deterministic:

```text
postgres healthcheck
-> migrate one-shot service runs alembic upgrade head
-> backend starts only after migrate exits successfully
-> proxy starts after backend healthcheck passes
```

## Health

```powershell
docker compose --env-file .env -f compose.prod.yaml ps
curl.exe -i http://127.0.0.1:8080/healthz
curl.exe -i http://127.0.0.1:8080/api/status
```

The backend liveness/readiness endpoint is `/api/status`. It executes a database `SELECT 1` and returns only service, environment, database status, and version.

## Logs

```powershell
docker compose --env-file .env -f compose.prod.yaml logs -f proxy
docker compose --env-file .env -f compose.prod.yaml logs -f backend
docker compose --env-file .env -f compose.prod.yaml logs -f postgres
```

Application logs go to stdout/stderr with timestamps and `X-Request-ID`. Do not log cookies, tokens, passwords, or raw request bodies.

## Data and Volumes

- `dripzone_postgres_data`: PostgreSQL data.
- `dripzone_uploads`: uploaded product/import files shared by backend and proxy.
- `./frontend/data`: bind-mounted public JSON data. The backend writes `products.json` atomically through `PUBLIC_PRODUCTS_PATH=/app/public-data/products.json`, and Caddy serves the same file at `/data/products.json`.
- `caddy_data` and `caddy_config`: Caddy runtime/certificate state.

Backup and restore procedures are documented in `docs/backup-restore.md`.

## Cache

- HTML and admin pages: `Cache-Control: no-cache`.
- `/data/products.json`: `Cache-Control: no-cache, must-revalidate`.
- `/api/*`: `Cache-Control: no-store`.
- Static assets: `Cache-Control: public, max-age=86400`.
- Uploads: `Cache-Control: public, max-age=604800`.

## Security Headers

The proxy adds:

- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`
- `X-Frame-Options: DENY`
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Resource-Policy: same-origin`

Local HTTP does not enable HSTS. Use `deploy/caddy/Caddyfile.https.example` for a real domain; it includes HSTS and lets Caddy obtain certificates automatically.

## HTTPS and Secure Cookies

`APP_ENV=production` makes the session cookie `Secure`. Browsers normally do not send `Secure` cookies over plain HTTP, so the local HTTP URL is suitable for static/API smoke tests, but not for a realistic admin login session.

Use these modes deliberately:

- Real production: keep `APP_ENV=production`, use HTTPS through Caddy, and keep `CORS_ORIGINS` on the real HTTPS origin.
- Local production-like HTTP: keep it for build, migration, health, static, API, upload, and catalog checks. Do not lower cookie security just to make login work over HTTP.
- HTTPS rehearsal: use a real test domain or an explicit local TLS setup before relying on browser auth behavior.

## HTTPS Later

1. Point DNS for the real domain to the server.
2. Set `DRIPZONE_SITE_ADDRESS=dripzone.com.br`.
3. Use the HTTPS Caddyfile example or add the HSTS header after validating HTTPS.
4. Expose host ports 80 and 443.
5. Keep `CORS_ORIGINS=https://dripzone.com.br`.

Do not enable HSTS until HTTPS is confirmed stable.

## Migrations

`compose.prod.yaml` includes a `migrate` one-shot service. It waits for PostgreSQL to be healthy, runs:

```powershell
python -m alembic upgrade head
```

and the backend starts only after that service exits successfully. For manual validation without starting the full stack, use:

```powershell
docker compose --env-file .env -f compose.prod.yaml run --rm migrate
```

## Restart and Stop

```powershell
docker compose --env-file .env -f compose.prod.yaml restart backend proxy
docker compose --env-file .env -f compose.prod.yaml down
```

Use `down -v` only when intentionally deleting volumes.

## Validation Commands

```powershell
docker compose --env-file .env -f compose.prod.yaml config
docker compose --env-file .env -f compose.prod.yaml build
docker compose --env-file .env -f compose.prod.yaml up -d
curl.exe -I http://127.0.0.1:8080/
curl.exe -I http://127.0.0.1:8080/data/products.json
curl.exe -I http://127.0.0.1:8080/api/status
curl.exe -I http://127.0.0.1:8080/healthz
```
