# Security boundary

This repository is intentionally incapable of real trading.

- Polymarket requests use public, unauthenticated data endpoints only; `POST /books` reads books.
- No wallet integration, wallet secrets, signing, authenticated Polymarket trading, trading SDK, or real order endpoint.
- No token approvals, transfers, deposits, withdrawals, position management, or geographic bypass.
- Geoblock response IP is discarded.
- Paper trades are local database records derived from validated public book snapshots.
- Unknown fees fail closed; stale or incomplete calculations cannot be labelled valid opportunities.

## Optional LLM translation credentials

User-provided LLM API keys authenticate only public-text translation. DeepSeek remains restricted to official HTTPS `api.deepseek.com` (base path empty or `/v1`). OpenAI-compatible providers must support Chat Completions and JSON output and use public HTTPS destinations on port 443. URL credentials/query/fragment, private or localhost destinations, non-public DNS resolutions and URLs ending in `/chat/completions` or `/models` are rejected. The backend appends `/chat/completions` to a base URL; redirects are disabled. Other API protocols are unsupported.

Named DeepSeek environment variables and an ignored local `.env` remain supported. Native website settings are saved atomically in ignored `data/llm-config.json` with Unix mode `0600`; they override environment defaults and survive restart. The file contains the credential and must remain private. API responses, application databases, translation caches, source and logs never contain the saved key or a key fragment. Removing website settings falls back to any environment key. An empty key can retain a credential only when the provider and normalized API base are unchanged; a new destination requires a new credential.

GET `/api/llm/config` returns same-origin public metadata without credentials. PUT/DELETE also require loopback host and peer checks, bounded JSON input for PUT, and same-origin browser requests. Website saves apply immediately and do not make a paid connection-test request. Docker bridge peers cannot write credentials even when the host browser uses localhost; configure container DeepSeek through ignored `.env` and recreate the container. These origin/local-peer checks do not replace a multi-user authorization layer.

The translation endpoint accepts only registered public market text, uses bounded batches and queues, validates response structure and numerical terms, and allows one corrective retry on the same configured model. Cache identity includes provider, API base, model, prompt version, target language and source. Configuration changes cancel old workers before activating the new provider and retain the public-text whitelist. Missing configuration does not return cached or local common-label translations. Failures retain the original source. Translation does not modify original data, outcome/token order, settlement identifiers, or Decimal financial calculations.

English is the initial website language and requests no market translations. Chinese requires a configured API key; fixed interface labels are bundled locally and newly visible public market text is translated on demand. A configured key is not proof of valid credentials, balance, model availability or protocol compatibility.

## Local runtime and publication

Bind to localhost. Local scanner settings, simulated-record, and translation routes have no user authentication; a public deployment requires an additional access-control boundary. Ignore `.env`, `data/llm-config.json`, virtual environments, databases (including translation caches), logs, and other runtime files when publishing source. Treat backups of `.env` and `data/` as private because they can include LLM credentials.

Run `python scripts/security_scan.py` before every release, alongside lint and tests. Its static checks cover selected executable/configuration file types and Git ignore rules; they complement manual publication review and do not prove that every possible secret or unsafe change has been excluded.
