# Architecture

`ScannerRuntime` owns the shared public Polymarket HTTP clients, `MarketCatalog`, Market WebSocket, in-memory scanner state, and SQLite storage. FastAPI serves the local browser, catalog/inspect APIs, scanner, monitor, records, settings, translation, and exports. The browser contacts the local server rather than Polymarket directly. The scope is public data and simulations; no wallet, signing, order submission, or fund movement exists.

The complete functional walkthrough, fixes, validation evidence, and limits are in [FUNCTIONAL_AUDIT.md](FUNCTIONAL_AUDIT.md). Endpoint contracts are in [API_REFERENCE.md](API_REFERENCE.md).

## Runtime and concurrency

Startup validates environment settings, initializes storage, marks prior active signals disappeared, and restores the validated five editable parameters from SQLite. Invalid persisted parameters leave valid environment defaults intact. Online startup warms the catalog/selection and initial books before service readiness, then launches periodic catalog, metadata, REST book, and WS tasks. Offline mode skips Polymarket tasks. Optional translation starts independently. Shutdown and startup failure clean up workers, sockets, clients, and databases.

A shared async refresh lock serializes market selection, REST book/result publication, parameter changes, and simulation saving. A calculation cannot combine an old token mapping or parameter group with a newly published selection. Simulation saving rechecks the same current gates and source books inside that lock. Background request/calculation failure clears candidate state and reconciles history; loops remain alive for recovery. Event logging failure cannot itself terminate a polling loop.

`/health` checks local database availability and returns 503 on failure. Upstream status, coverage, and quote freshness are independent monitor fields. Browser polling pauses while hidden; backend sampling continues. Request sequence numbers, cancellation, timeouts, and in-flight guards prevent older browser responses or duplicate saves from corrupting the current view.

## Catalog and current market lifecycle

Gamma event seed queries supply popular/new/category coverage. Keyset traversal builds a private draft, capped at 100 pages of 100 events, then atomically publishes normalized items, raw mappings, category aggregates, refresh time, and revision. Failed traversal preserves the last published snapshot while reporting failure separately. A complete traversal removes seed-only entries no longer returned; capped coverage remains explicit. Invalid pagination and unsafe display amounts cannot be reported as complete or produce non-finite JSON.

Scanner liquidity/total-volume thresholds apply before category-balanced allocation. Catalog preselection diagnostics are distinct from fresh Gamma verification results. Every selected market is rechecked through batched `/markets?id=...` before reuse; closed/missing/paused markets, changed condition IDs, and changed original outcome/token positions do not enter the current scanner. Catalog absence uses a fresh bounded markets-keyset fallback.

A strictly matched `market_resolved` event removes the market from catalog and scanner state. The catalog retains a process-local terminal set so stale seeds, in-progress drafts, or failure fallback cannot revive it. Unknown lifecycle events cannot clear arbitrary catalog entries.

## Books, financial calculation, and display

Normalization is separate from network access. Outcome/token mapping follows original array positions. Each orderbook belongs to a real requested asset and is normalized/sorted before the pure Decimal calculator consumes it.

Two book stores have different roles:

- `books` contains display snapshots from REST or complete WS `book` messages. Current subscriptions and source timestamps prevent unrelated or older messages from overwriting newer books.
- `calculation_books` retains the independent REST batch published with the calculation results. WS updates never change these inputs. Detail APIs label and expose both sources.

The Market WS sends heartbeats on a fixed ten-second deadline even on busy connections. Token changes trigger reconnection. Complete-message deduplication is bounded and cleared on reconnect; failed handling is not permanently deduplicated. Current calculation books are not reconstructed from WS delta messages.

Depth calculation consumes each ask level for the common quantity, calculates settlement value and supported known fees, then subtracts cost buffers and other costs. Total-budget ROI includes those costs. Input identity/condition validation, invalid/crossed books, and extreme Decimal arithmetic produce explicit unusable results. Fee exemption is known zero; fee-enabled markets require a supported explicit rate/exponent. Unknown fees never silently become zero.

Scanner gates additionally require fresh matching source books, known minimum sizes, complete target execution, current upstream state, and configured minimum profit/ROI. Source age is rechecked when serving a candidate or saving a simulation. API display copies change valid-like retained results to STALE when expired or unknown without mutating the original result; structural errors retain priority. A mathematical VALID result alone does not establish a scanner candidate.

The pure `book_analytics` module provides Decimal liquidity summaries per actual token. Quality and freshness remain separate from profit gates. Inspect requests first verify fresh Gamma state/mapping, then retrieve current books; non-Yes/No binary labels preserve original display order. Larger outcome sets currently receive descriptive analytics only.

## Persistence and local configuration

Five editable Decimal parameters share API/startup validation. SQLite saves the group in one transaction; runtime uses an atomic settings copy and clears results until the next calculation. Other settings remain environment configuration.

Valid signals use fingerprints incorporating full book identity/content and calculation inputs. Each refresh reconciles active/disappeared history; identical inputs may reactivate the same fingerprint. Simulations are independently saved observations, including repeated intentional observations of a candidate. Estimated simulation totals sum SUCCESS records and do not represent realized account profit.

Signal and simulation payloads include audit context: public REST source, as-of time, original market mapping, parameters, and actual two book inputs. List APIs return lightweight summaries; ID detail APIs return full saved audit data. Existing older records may lack the newly captured inputs. No complete market-book archive or automatic history retention job is implemented.

CSV exports stream all stored rows with stable headers, UTF-8 BOM, and formula-text escaping. Record timestamps are explicitly serialized in UTC; the UI formats Asia/Shanghai times. Credentials, databases, logs, exports, `.venv`, and caches stay local and ignored by Git.

## Translation and provenance

`TranslationService` uses a separate official-host-only DeepSeek client and SQLite cache. Only registered public text can enter bounded workers; common outcome labels can translate locally. Cache identity includes model, prompt version, target language, and source hash. The cheapest configured Flash model uses thinking disabled and one bounded corrective retry. Response validation protects numbers, symbols, URLs, IDs, and batch completeness.

The browser observes newly visible text, requests translations, and restores original market fields in English mode. Translation affects display only and never changes source data or financial inputs. Failed translation preserves original text with an explicit status; semantic correctness still requires checking original rules.

Source-level reference/adoption decisions are recorded in [OPEN_SOURCE_REVIEW.md](OPEN_SOURCE_REVIEW.md). No additional third-party trading SDK is integrated. Upstream provenance and retained license are documented in [UPSTREAM.txt](../UPSTREAM.txt).
