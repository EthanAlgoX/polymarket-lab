# Architecture

`ScannerRuntime` owns the shared public Polymarket HTTP clients, `MarketCatalog`, a Market WebSocket, in-memory market/book state, and the scanner SQLite database. Background loops discover a capped event catalog, refresh a bounded scanner selection, poll CLOB books, and maintain WebSocket subscriptions. Coverage and quote freshness are reported separately. Shutdown cancels tasks, closes clients/sockets, and disposes storage.

Market normalization is separated from network code. Outcome/token mapping follows original array positions. Orderbooks are normalized and sorted before the pure Decimal depth calculator sees them. Scanner gates reject stale, partial, unknown-fee, undersized, or below-threshold results. Profit calculations use REST snapshots; a connected WebSocket is not a freshness guarantee.

FastAPI serves the catalog, inspect/scanner APIs, rendered pages, local history, and settings. The browser calls this local server; it does not contact Polymarket directly.

The optional `TranslationService` uses a separate, official-host-only DeepSeek client and SQLite cache. Only public text registered by the local APIs may be queued. The browser language layer observes new displayed text, requests translations, and restores originals in English mode. Translation never changes source data or calculation inputs.

Runtime files (`.env`, `.venv`, `data/`, `logs/`, exports, and caches) remain local and are ignored by Git. Upstream provenance is documented in `UPSTREAM.txt`.
