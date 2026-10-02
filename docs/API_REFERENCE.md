# API reference

Implementation reviewed on **2026-10-03 (Asia/Shanghai)**. This describes the checked-in behavior. Validation results and actual limitations are recorded in [FUNCTIONAL_AUDIT.md](FUNCTIONAL_AUDIT.md). Data comes directly from public Polymarket APIs; no HTML scraping or third-party trading SDK is used.

## Polymarket data sources

Gamma base: `https://gamma-api.polymarket.com`.

- `GET /events/keyset` is the primary catalog source. Requests use `active=true`, `closed=false`, `limit=100`, ordering/tag filters, and opaque `after_cursor`. Responses contain `events` and `next_cursor`; event children supply markets, outcomes, token IDs, prices, tags, liquidity, volume, and settlement rules.
- Initial seed requests cover popular/new events and selected category tags. Traversal requests at most 100 pages of 100 events. One event may contain many child markets; the cap is not a market count or a guarantee of complete platform coverage.
- The catalog loop waits 600 seconds after each traversal. The bounded scanner selection refreshes at `PMS_MARKET_REFRESH_SECONDS` (default 60). Each selection is rechecked through `GET /markets` with repeated `id` query parameters in batches of at most 100. Closed, missing, paused, or remapped markets cannot produce current scanner candidates.
- `GET /markets/keyset` remains a fallback if no catalog is available. The client checks termination flags and cursors. Outcome and token arrays may be JSON strings; their shared index determines the mapping.

CLOB base: `https://clob.polymarket.com`.

- `POST /books` reads books in batches of up to 500 `{ "token_id": "..." }` objects. It is a public read request. Fields include `asset_id`, `market`, `timestamp`, `hash`, `bids`, `asks`, `tick_size`, and `min_order_size`. Only requested assets are accepted.
- Book polling uses `PMS_REST_REFRESH_SECONDS` (default 5). Calculations retain a separate REST batch and validate identity, quote age, fee information, and known minimum order sizes. WS display updates never change the calculation inputs.
- A `GET /clob-markets/{condition_id}` fee helper is retained; it reads `fd.r` and `fd.e`. The current scanner and inspect route instead use fresh Gamma `feesEnabled` / `feeSchedule`. Explicit fee exemption is known zero. Otherwise a finite nonnegative rate and explicit supported exponent `1` are required. Missing, invalid, or unsupported fee data fails closed.
- Public GET requests and the read-only POST `/books` make at most three attempts for timeout/network errors, 429, 5xx, or invalid JSON. Backoff uses jitter and honors valid Retry-After seconds/HTTP dates, capped at 30 seconds, with a shared cooldown per origin. Waiting releases the request semaphore. Other 4xx responses fail immediately. Typed errors and request logs omit response bodies, credentials, and query strings. No Polymarket authentication or trading endpoints are used.

Market WebSocket: `wss://ws-subscriptions-clob.polymarket.com/ws/market`.

```json
{"assets_ids":["TOKEN_ID"],"type":"market","custom_feature_enabled":true}
```

The client sends `PING` every ten seconds even while ordinary messages arrive, accepts `PONG`, and reconnects when its token set changes. Deduplication uses the complete canonical message with a bounded cache, cleared on connection establishment. A frame is cached only after successful handling; distinct messages with the same timestamp remain deliverable. Handler failure is isolated to the affected frame.

`book` events update display snapshots. Unknown or outdated subscriptions and older timestamps cannot overwrite a newer known display book. A strictly matching `market_resolved` event removes that market and retains its terminal state in the current process. The client does not reconstruct calculation books from `price_change` deltas. A WS connection alone does not establish calculation freshness.

`GET https://polymarket.com/api/geoblock` is informational. The response IP is discarded before persistence/display; no bypass logic exists.

Official schema references: [Gamma list markets](https://docs.polymarket.com/api-reference/markets/list-markets), [CLOB market information](https://docs.polymarket.com/api-reference/markets/get-clob-market-info), [fees](https://docs.polymarket.com/trading/fees), and [Market WebSocket](https://docs.polymarket.com/api-reference/wss/market).

## Local application endpoints

| Endpoint | Purpose and main bounds |
| --- | --- |
| `GET /api/catalog` | Cached directory, category summaries, coverage, timestamps, revision, and scanner/candidate counts. `category`: all/sports/weather/crypto/economy/politics/other; `search`: original question/event text, max 500 characters; `min_liquidity`: finite and ≥0; `sort`: volume24h/liquidity/newest/ending; `limit`: default 40, range 1–200; `offset`: ≥0. |
| `GET /api/inspect/{market_id}` | Recheck current Gamma trading state and original mapping, then fetch fresh books. `quantity`: default 100, range 1–100000; `extra_cost`: default 0.05, range 0–10000. Two distinct outcomes receive a cost estimate; larger outcome sets receive descriptive books only. |
| `GET /api/markets` | Current bounded scanner selection with dynamic candidate/freshness checks. `limit`: default 50, range 1–200; `offset`: ≥0. |
| `GET /api/markets/{market_id}` | Scanner calculation, Yes/No display books, analytics, and the separate REST calculation books. Unknown scanner market: 404. |
| `GET /api/opportunities` | Current scanner results passing every candidate gate. An empty response describes this selection, not the entire platform. |
| `GET /api/opportunities/history` | Persisted signal summaries. `limit`: default 100, range 1–500; `offset`: ≥0. |
| `GET /api/opportunities/history/{opportunity_id}` | Full saved signal details and audit inputs; missing ID: 404. |
| `POST /api/paper-trades` | Body `{ "market_id": "..." }`, ID length 1–64. Recheck a current scanner candidate under the refresh lock, then save a simulation. Missing, expired, or invalid snapshot: 409. Response includes `simulation_only: true`. |
| `GET /api/paper-trades` | Persisted simulation summaries. `limit`: default 100, range 1–500; `offset`: ≥0. |
| `GET /api/paper-trades/{trade_id}` | Full saved simulation details and audit inputs; missing ID: 404. |
| `GET /api/settings`, `PUT /api/settings` | Read/write the five validated scanner parameters below. |
| `GET /health` | Local database health; JSON 200 when healthy, 503 when degraded. This does not verify upstream data freshness. |
| `GET /api/system/status` | Runtime/upstream/WS/database state, sample counts, current candidate count, catalog selection, and public HTTP counters. |
| `GET /api/dashboard` | Runtime status, saved simulation count, and the sum of SUCCESS simulation estimates. The sum is not realized profit. |
| `GET /api/logs` | Sanitized local events; `limit`: default 100, range 1–500. |
| `GET /api/research` | Checked-in strategy/reference material; stars are a dated snapshot. |
| `GET /api/exports/opportunities.csv`, `GET /api/exports/paper-trades.csv` | Complete streamed CSV exports using original text. |
| `POST /api/translations` | Queue/retrieve translations of registered public market text; detailed limits below. |

Invalid request parameters return FastAPI validation errors (422). Built-in local schema views are `/docs`, `/redoc`, and `/openapi.json`. The application has no multi-user authorization layer; its launch defaults bind locally.

### Catalog snapshots and coverage

`/api/catalog` returns one published `revision` for items and category aggregates. Coverage states are `loading`, `sample`, `paginated`, `capped`, and `partial`. `coverage` reports the latest crawl, while `dataCoverage` describes retained data. A failed refresh retains the previous published data and refresh time. A complete traversal removes seed-only markets no longer returned; a capped traversal may retain seed coverage. Extreme display amounts are omitted and counted in `invalidRecords` so JSON cannot contain infinite numbers.

`scannerSelection` contains liquidity/total-volume thresholds, eligible/selected counts, category counts, and exclusions. Selection reserves up to eight rounds across categories, then fills by 24-hour volume, liquidity, and ID. `selectedTotal` and top-level `categoryCounts` describe catalog preselection. `verification` contains `sourceRevision`, `requestedTotal`, `verifiedTotal`, actual `categoryCounts`, `verifiedAt`, and `failed` for the subsequent current-Gamma check. Metadata failure clears calculations and candidates while retaining marked older display data.

`liveScannerEnabled` identifies deliberate offline mode; `/api/system/status` exposes the same setting as `live_scanner_enabled`. `verifiedAt` and inspection `metadataAsOf` are local successful API receipt times. Gamma responses observed during this evaluation carried a 300-second cache lifetime, so these times do not guarantee source metadata was just updated. No cache bypass is used. CLOB book `timestamp` is the source snapshot time, independent of local REST receipt (`asOf` / `calculation_as_of`); fetching a quiet book again does not renew it. See [evaluation evidence](FEATURE_EVALUATION.md).

### Inspect and scanner calculation sources

`/api/inspect/{market_id}` returns 404 if the market is absent from the catalog. If fresh Gamma data omits the market, reports closed/paused, or changes condition/outcome/token mapping, the route returns 200 with `available: false`, `unavailableReason`, null books/analytics/calculation, and observation times. Public metadata/book retrieval failure returns 502. Successful inspection uses current fees and only the requested outcome books. Output preserves original outcome/token order, including team-name or Up/Down pairs.

`/api/markets/{market_id}` uses explicit Yes/No order. `yes_orderbook`, `no_orderbook`, and `book_analytics` describe display books, which may come from REST or WS. `calculation_orderbooks` and `calculation_as_of` identify the REST inputs underlying the retained calculation; `display_orderbooks_source` explains the display source. Display and calculation timestamps may differ.

Analytics fields are Decimal strings or null: spread, midpoint, spread basis points, best-level sizes/imbalance/microprice, and bid/ask quantity/collateral within 0.02 of each best price. `quality` distinguishes normal, unavailable, one-sided, crossed, and invalid books. `stale` and `quote_age_seconds` independently describe freshness.

Timestamp validation rejects missing, non-finite, non-positive, or more than one second future timestamps. Two-leg age uses the oldest REST source and conservative elapsed age. Clock rollback or unknown source time blocks candidates. Retained VALID/PARTIAL/FEE_UNKNOWN calculations are displayed as STALE once unknown or expired; structural invalid statuses retain priority. Missing minimum order size blocks candidates. `VALID` describes a complete mathematical estimate; `is_candidate` additionally requires current metadata, sources, size, and profit/ROI gates.

### Parameters and persistence

`PUT /api/settings` requires all five fields (finite Decimal values; JSON numbers or decimal strings):

| Field | Bound |
| --- | --- |
| `minimum_net_profit` | 0–1000 |
| `minimum_net_roi` | 0–1 |
| `default_quantity` | >0 and ≤100000 |
| `slippage_rate` | 0–0.25 |
| `safety_rate` | 0–0.25 |

Saving uses a single database transaction and atomically replaces runtime settings under the refresh lock. It clears old calculations and candidates, marks old signals disappeared, and waits for a new successful book calculation. Startup restores the validated persisted group; invalid persisted values retain valid environment defaults and produce a sanitized CONFIG error. Other scanner settings remain startup configuration.

History states describe persisted observations (`active`/`disappeared`), not current execution permission. Each new calculation reconciles current fingerprints; failure, market/parameter changes, or restart invalidate old active signals. A matching fingerprint can become active again. Fingerprints include book identity/content and calculation inputs.

List endpoints contain summaries. The history/simulation detail endpoints expose `details.audit` containing source, as-of time, original market mapping, parameters, and the actual two REST books. Older records may lack audit fields. Repeated intentional simulation observations are allowed; no real order is submitted.

CSV exports iterate every saved row in 500-row chunks, regardless of API list limits. They contain fixed headers and UTF-8 BOM, including an empty database. Formula-looking text beginning with `=`, `+`, `-`, or `@` after leading whitespace is prefixed with an apostrophe; validated numeric columns retain numbers. Stored record times are serialized with an explicit UTC offset; the browser formats them in Asia/Shanghai.

`/api/system/status.public_http` includes calls, attempts, retries, rate-limited responses, last status, and last retry delay. `scanner_selection` exposes the current selection diagnostics. Live backend polling continues while browser polling pauses in hidden tabs.

## Display-only translation

`POST /api/translations` accepts `{ "texts": ["..."] }`: 1–80 strings, at most 20000 characters each and 100000 in total. Only public market text already served by the app, supported common outcome labels, or registered lossless segments of long rules may be translated. Responses include `items` with `source`, `text`, and `status` (`ready`, `pending`, or `error`), plus provider/model availability. Poll to retrieve queued results.

Optional server credentials are read from `DEEPSEEK_API_KEY` (also `DEEPSEEK_KEY` / `PMS_DEEPSEEK_API_KEY`) or an ignored local `.env`. Requests go only to `https://api.deepseek.com/chat/completions` or the official `/v1` equivalent, using `deepseek-flash` (DeepSeek V4.1 Flash), thinking disabled, and JSON output. The bounded worker queue batches requests; successful translations persist in `data/translations.sqlite3`, keyed by model, prompt version, target language, and full source hash. One corrective retry uses the same model.

Validation preserves numeric occurrence counts, protected symbols, URLs, response IDs, and complete batches. Missing credentials, request errors, or failed validation retain original text with an explicit status. Retry is bounded; the browser offers an explicit retry rather than an unlimited paid loop.

The default browser preference is Chinese; English restores original market fields. The switch translates market content, while fixed application controls remain mainly Chinese. Translation never changes source prices, quantities, IDs, outcome/token ordering, rules, or Decimal inputs. Source-language rules remain authoritative; syntax validation cannot establish semantic correctness. Catalog search and CSV exports retain original text.
