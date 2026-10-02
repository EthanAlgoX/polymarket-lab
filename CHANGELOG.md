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

## [0.1.0] - 2026-10-02

### Added

- Event-based market catalog with categories, pagination, and explicit coverage limits.
- Public Gamma/CLOB/Market WebSocket clients, REST snapshot scanning, and Decimal depth calculations.
- Fail-closed fees, quote-age checks, minimum-size gates, and all-in paper opportunity estimates.
- Research interface and shared responsive sidebar for the scanner, monitor, history, and settings.
- Optional backend DeepSeek translation, Chinese/English switching, and persistent translation caching.
- Local SQLite records, CSV exports, macOS/Windows launchers, Docker, tests, and CI.

The scanning foundation is adapted from the MIT-licensed Polymarket Market Scanner; see `UPSTREAM.txt`.
