# API reference

Implementation reviewed on **2026-10-02 (Asia/Shanghai)**. This describes the checked-in code; live availability must be verified separately. Data comes directly from public Polymarket APIs, without HTML scraping or a third-party trading SDK.

## Polymarket data sources

Gamma base: `https://gamma-api.polymarket.com`.

- `GET /events/keyset` is the primary catalog source. Requests use `active=true`, `closed=false`, `limit=100`, ordering/tag filters, and opaque `after_cursor`. Responses contain `events` and `next_cursor`; event children supply markets, outcomes, token IDs, prices, tags, liquidity, volume, and settlement rules.
- Initial seed requests cover popular/new events and selected category tags. Traversal then requests at most 100 pages of 100 events. This cap applies to events, each of which may contain many child markets. Coverage is reported as `loading`, `sample`, `paginated`, `capped`, or `partial`; capped/partial results are not a guarantee of complete platform coverage.
- The catalog loop waits 600 seconds after each traversal. The bounded scanner selection refreshes at `PMS_MARKET_REFRESH_SECONDS` (default 60); it does not scan every catalog item.
- `GET /markets/keyset` remains a fallback if no catalog is available. Outcome and token arrays may be JSON strings; their shared index determines the mapping.

CLOB base: `https://clob.polymarket.com`.

- `POST /books` reads books in batches of up to 500 `{ "token_id": "..." }` objects. It is a public read request, not order submission. Fields include `asset_id`, `timestamp`, `hash`, `bids`, `asks`, `tick_size`, and `min_order_size`.
- Book polling uses `PMS_REST_REFRESH_SECONDS` (default 5). Calculations use REST snapshots and validate quote age, fee information, and minimum order size.
- A `GET /markets/{condition_id}` fee helper is retained, but the current scanner and inspect route use Gamma `feesEnabled` / `feeSchedule`. A fee-enabled market requires a finite nonnegative rate and supported exponent `1`; unknown fee information fails closed.
- The public HTTP client makes at most three attempts for timeout/network errors, 429, 5xx, or invalid JSON, with backoff. Other 4xx responses fail immediately. No Polymarket authentication or trading endpoints are used.

Market WebSocket: `wss://ws-subscriptions-clob.polymarket.com/ws/market`.

```json
{"assets_ids":["TOKEN_ID"],"type":"market","custom_feature_enabled":true}
```

The client sends `PING` after ten seconds without a message, accepts `PONG`, and reconnects when its token set changes. `book` events update displayed books; profit calculations continue to use REST snapshots. A WebSocket connection alone does not establish that a calculation is current.

`GET https://polymarket.com/api/geoblock` is informational. The response IP is discarded before persistence/display, and no bypass logic exists.

## Local application endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/catalog` | Cached catalog, category summaries, coverage, refresh time, and scanner/candidate counts. Filters: `category`, `search` (original question/event text), `min_liquidity`; sorts: `volume24h`, `liquidity`, `newest`, `ending`; `limit` 1–200, `offset` ≥0. |
| `GET /api/inspect/{market_id}` | Fetch current public books for a catalog market. For two mapped outcomes, calculate depth with `quantity` (default 100, range 1–100000) and `extra_cost` (default 0.05, range 0–10000). Display preserves original outcome/token order. |
| `GET /api/markets`, `GET /api/markets/{market_id}` | Bounded scanner selection and latest calculations/books. |
| `GET /api/opportunities` | Current scanner results that pass every candidate gate. An empty response describes this selection, not the entire platform. |
| `GET /api/opportunities/history`, `GET /api/paper-trades` | Local historical signals and simulated records. |
| `POST /api/paper-trades` | Record a simulation from a valid current snapshot; never submit a real order. |
| `GET /api/settings`, `PUT /api/settings` | Local scanner thresholds and buffers. |
| `GET /health`, `GET /api/system/status`, `GET /api/dashboard`, `GET /api/logs` | Local health, runtime status, simulation totals, and sanitized event logs. |
| `GET /api/research` | Checked-in strategy/reference material. |
| `GET /api/exports/opportunities.csv`, `GET /api/exports/paper-trades.csv` | Local CSV exports using original text. |

## Display-only translation

`POST /api/translations` accepts `{ "texts": ["..."] }`: 1–80 strings, at most 20000 characters each and 100000 in total. Only public market text already served by the app (or supported common outcome labels / lossless segments of long rules) may be translated. Responses include `items` with `source`, `text`, and `status` (`ready`, `pending`, or `error`), plus provider/model availability. Poll to retrieve queued results.

Optional server-side credentials are read from `DEEPSEEK_API_KEY` (also `DEEPSEEK_KEY` / `PMS_DEEPSEEK_API_KEY`) or an ignored local `.env`. Requests go only to `https://api.deepseek.com/chat/completions` or the official `/v1` equivalent, using `deepseek-flash` (DeepSeek V4.1 Flash), thinking disabled, and JSON output. Requests are batched; successful translations persist in `data/translations.sqlite3`. One corrective retry uses the same model. Missing credentials or failed validation return an explicit error and retain the original English text.

Translation changes display text only. Prices, quantities, identifiers, outcome/token order, settlement rules in the source data, and Decimal calculations remain unchanged. English source rules remain authoritative.
