# Security boundary

This repository is intentionally incapable of real trading.

- Polymarket requests use public, unauthenticated data endpoints only; `POST /books` reads books.
- No wallet integration, wallet secrets, signing, authenticated Polymarket trading, trading SDK, or real order endpoint.
- No token approvals, transfers, deposits, withdrawals, position management, or geographic bypass.
- Geoblock response IP is discarded.
- Paper trades are local database records derived from validated public book snapshots.
- Unknown fees fail closed; stale or incomplete calculations cannot be labelled valid opportunities.

## Optional DeepSeek exception

An existing DeepSeek API key may be read exclusively on the backend from named environment variables or an ignored local `.env`. It authenticates only public-text translation requests to the official HTTPS `api.deepseek.com` endpoint. Redirects and nonofficial destinations are rejected. The key is never returned to the browser or written to source, caches, or logs.

The translation endpoint accepts only registered public market text, uses bounded batches and queues, validates response structure and numerical terms, and allows one corrective retry on the same cheap model. Approved text translations are cached locally; failures retain the original source. Translation does not modify original data, outcome/token order, settlement identifiers, or Decimal financial calculations.

## Local runtime and publication

Bind to localhost. Local settings, simulated-record, and translation routes have no user authentication; a public deployment requires an additional access-control boundary. Ignore `.env`, virtual environments, databases (including translation caches), logs, and other runtime files when publishing source.

Run `python scripts/security_scan.py` before every release, alongside lint and tests. Its static checks cover selected executable/configuration file types and Git ignore rules; they complement manual publication review and do not prove that every possible secret or unsafe change has been excluded.
