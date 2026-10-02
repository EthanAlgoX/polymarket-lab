# Changelog

## Unreleased

- Added an evidence-backed high-star project review and archive/star filters in the reference page.
- Added Decimal orderbook-quality summaries for each outcome, with invalid-book and freshness labels.
- Added bounded Retry-After handling, shared per-origin cooldown, sanitized typed errors, and public HTTP counters.
- Fixed WebSocket deduplication for distinct messages sharing a timestamp and initial snapshots after reconnection.
- Reject invalid/future quote timestamps consistently in detail analytics and financial gates using shared Decimal time validation.
- Published catalog revisions atomically; preserve the last published data on refresh failure and reject repeated cursors.
- Apply scanner thresholds before category allocation and expose the resulting category mix.
- Expanded deterministic tests for these request, catalog, message, and data-quality boundaries.
- Audited the full application flow and documented pages, APIs, lifecycle, fixes, validation evidence, and actual limits in `docs/FUNCTIONAL_AUDIT.md`.
- Recheck selected/inspected markets against fresh Gamma trading state and mappings; remove resolved markets without reviving them from stale catalog drafts or fallbacks.
- Serialize metadata/book publication, parameter changes, and simulation saving; clear invalid candidates on failures and keep polling tasks alive for recovery.
- Preserve separate REST calculation books and audit inputs alongside WS display snapshots; expose read-only historical/simulation detail APIs.
- Enforce pair/condition identity, known minimum sizes, explicit fee exponents, conservative quote age, and invalid/crossed/extreme Decimal input handling. Expired retained calculations now display STALE.
- Send WS heartbeats on busy connections and isolate failed frames while rejecting unrelated/older display books.
- Validate and atomically persist all five editable parameters, restore them at startup, and reconcile active/disappeared signal history across refresh, failure, changes, and restart.
- Add historical/simulation pagination, complete streamed CSV exports with formula-text escaping, UTC record timestamps, and degraded database health status 503.
- Protect translated numbers, symbols, URLs, response completeness, and cache versions; bound paid retries and preserve originals on failure.
- Harden frontend request ordering, timeout/error states, unsaved parameter input, candidate labels, duplicate in-flight saves, and accessible responsive market drawers.
- Use a shared validated `python -m app` entry point for local/Windows host and port settings; ensure cleanup after failed startup.

## [0.1.0] - 2026-10-02

### Added

- Event-based market catalog with categories, pagination, and explicit coverage limits.
- Public Gamma/CLOB/Market WebSocket clients, REST snapshot scanning, and Decimal depth calculations.
- Fail-closed fees, quote-age checks, minimum-size gates, and all-in paper opportunity estimates.
- Research interface and shared responsive sidebar for the scanner, monitor, history, and settings.
- Optional backend DeepSeek translation, Chinese/English switching, and persistent translation caching.
- Local SQLite records, CSV exports, macOS/Windows launchers, Docker, tests, and CI.

The scanning foundation is adapted from the MIT-licensed Polymarket Market Scanner; see `UPSTREAM.txt`.
