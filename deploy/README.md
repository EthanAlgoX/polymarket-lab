# Authenticated server deployment

[English](README.md) · [简体中文](README_CN.md)

Run this research workspace under `/polymarket-lab/` alongside existing websites.
Use **one app process**, an authenticated HTTPS Nginx proxy, and an unused loopback
port. Public market collection continues when the local computer is off. Market
API failures remain visible; a healthy HTTP server does not prove fresh quotes.

The server example requires Linux, Docker Engine, and Docker Compose ≥2.24.
Its host network keeps the application on `127.0.0.1:8011`, and makes the proxy's
loopback address explicit. Desktop Docker continues to use the repository's
separate `docker-compose.yml`.

## Install

Place reviewed source at `/opt/polymarket-lab/app`. Do not upload a macOS venv,
local `.env`, API keys, databases, logs, or translation caches with source.

```sh
sudo install -d -m 700 -o 10001 -g 10001 /opt/polymarket-lab/data /opt/polymarket-lab/logs
cd /opt/polymarket-lab/app/deploy
cp .env.example .env
chmod 600 .env
```

Set your exact HTTPS origin in `PMS_CONFIGURATION_ORIGIN`, and confirm port 8011
is unused. `PMS_ROOT_PATH=/polymarket-lab` prefixes pages, assets, APIs, exports,
market inspection links, and Swagger schema URLs. Keep a trailing slash on the
public entry point.

```sh
sudo docker compose -p polymarket-lab build
sudo docker compose -p polymarket-lab up -d
sudo docker compose -p polymarket-lab ps
curl --fail http://127.0.0.1:8011/health
```

The image runs as UID/GID `10001:10001`. Database, translations, saved API
configuration and logs persist in the two host directories across recreation.
Container stdout rotates; app log retention is separate. A Docker health check
reports availability; `restart: unless-stopped` restarts an exited process, not
an unhealthy process which is still running.

## HTTPS and API settings

Adapt [nginx-subpath.conf.example](nginx-subpath.conf.example) inside your existing
HTTPS server block. Protect **the entire path**, including pages, static files,
APIs, translations, configuration and exports, with your existing authenticated
access boundary. The application does not implement user accounts or per-user
credentials: authorized visitors share scanner state and the server's translation
API configuration. Never remove proxy authentication because data sources are public.

Nginx strips `/polymarket-lab/` before forwarding. It overwrites forwarded scheme
and address headers and removes its login header. Only loopback proxy headers are
trusted. Check `nginx -t` before reloading; preserve existing locations, services,
password files and certificates.

`PMS_CONFIGURATION_ORIGIN` explicitly enables hosted API configuration. It is an
**origin check, not authentication**. Leave it empty for local-only credential
changes. Hosted saves/removals require the exact HTTPS origin and same-origin
request headers. Browser saves apply immediately without a restart or paid API
test; the key is stored in owner-only `data/llm-config.json` and never returned.
English needs no key. After logging in, configure your own LLM in **Settings →
Translation API**, then select **中文**. No laptop key is copied automatically.

## Verify and update

Verify unauthenticated page/API requests return 401; authenticated requests to all
seven pages, static assets, `/health`, `/api/system/status`, `/api/catalog`,
`/api/llm/config`, `/docs` and CSV exports work under the prefix. Check category
filtering, market inspection, mobile navigation and the no-key Chinese prompt.
Use a malformed configuration request to verify access/validation without storing
a key or spending translation credits. Confirm existing sibling sites still work.

For updates, build a versioned image before replacing the container; preserve
`deploy/.env`, data and logs. Save the current image tag and proxy configuration.
Back up SQLite consistently with `sqlite3.Connection.backup`, and keep backups of
API configuration private. Roll back the image/proxy configuration while retaining
the latest data. Never restore an old database over new observations as part of
a code rollback. Check a persisted deployment receipt before repeating an operation
whose result is unknown.
