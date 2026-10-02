# Polymarket Lab

**[English](README.md) · [简体中文](README_CN.md)**

A local, public-data-only Polymarket research workspace: browse open markets by category, inspect actual outcome books, estimate two-outcome complete-set costs, and observe a bounded scanner. It reads official Gamma, CLOB, and Market WebSocket APIs directly. No website scraping, wallet connection, signing, orders, transfers, holdings, or realized account profit is implemented.

The website starts in **English**. To use Chinese, configure your own translation API in **Settings → Translation API**, then choose **中文**. Docker uses backend `.env` configuration instead. If no API key is configured, the site stays in English and offers a configuration link. The Chinese README is maintained alongside this file and can be read without any API key.

**An estimate is not a fill.** Mathematical `VALID`, positive estimated difference, and passing every current scanner gate are separate results. Zero candidates can be a healthy outcome. Sports/weather/crypto strategy pages and high-star repositories are dated research references; they do not provide validated predictions or guaranteed income.

Follow the A–E acceptance stages below. [FEATURE_EVALUATION.md](docs/FEATURE_EVALUATION.md) records actual execution evidence separately from mocked/synthetic cases and untested platforms. Detailed contracts: [API](docs/API_REFERENCE.md), [calculation](docs/CALCULATION.md), [architecture](docs/ARCHITECTURE.md), [functional audit](docs/FUNCTIONAL_AUDIT.md), [open-source review](docs/OPEN_SOURCE_REVIEW.md).

![English workspace. Market counts and prices are live snapshots.](docs/images/overview-en.png)

## A. Install and start

Prerequisites: Git, **Python ≥3.11** (3.12 recommended), and network access to package installation and public Polymarket endpoints. Python runs the application; **Node.js ≥18 is needed only for the complete frontend regression suite**. No npm build or Polymarket account/API key is required. English works without an LLM API; Chinese market translation uses your provider's credits only when requested.

```sh
git clone https://github.com/EthanAlgoX/polymarket-lab.git
cd polymarket-lab
```

### macOS launcher

```sh
cp .env.example .env
./start-local.command
```

The launcher creates the project-local `.venv` and installs locked runtime dependencies when necessary. Set `PM_PYTHON` to a Python executable if automatic detection fails. If no translation key is inherited, the launcher loads the user's interactive zsh environment, which may already contain one. Keep the terminal open; stop with Ctrl+C.

### macOS / Linux manual setup

```sh
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
cp .env.example .env
python -m app
```

Run from the repository directory: relative `.env`, database, and log paths belong there. `python -m app` honors validated `PMS_HOST` / `PMS_PORT`. If port 8000 is occupied, set `PMS_PORT=8127` in `.env` and open port 8127 instead.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Start with the catalog and monitor. For Chinese, follow [Language and your translation API](#language-and-your-translation-api); native local installations can save an API through the website without editing source or restarting.

### Windows

With Python ≥3.11 available as `python`, run in PowerShell:

```powershell
.\install.bat
.\run.bat
```

The installer creates `.venv`, installs locked runtime dependencies, creates `.env` only if absent, and initializes the schema. Development checks are a separate step. Manual setup avoids PowerShell activation policy changes:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m app
```

### Docker

Requires Docker and **Docker Compose ≥2.24.0** for optional `env_file` support ([Docker documentation](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)).

```sh
cp .env.example .env
docker compose up --build
```

Compose can read the ignored project `.env`. The container binds 0.0.0.0:8000 and uses `/app/data/scanner.db`; those three Compose settings override corresponding `.env` values. The host mapping stays **127.0.0.1:8000**. Named volumes persist the container's database/cache/logs separately from local `data/` and `logs/`. `docker compose down` stops the service and retains those volumes; do not add `-v` when preserving records. The image uses locked dependencies and runs as a non-root user.

For Chinese in Docker, put `DEEPSEEK_API_KEY` in the ignored `.env` before starting. After editing it, run `docker compose up -d --force-recreate` to load the new environment, then choose 中文. The website can read API status, but **Save API settings / Remove saved settings are unavailable through Docker's bridge network** because credential writes require a loopback peer. Container translation configuration therefore uses `.env`; do not put credentials in the image or Compose file.

Platform execution evidence is in [the evaluation](docs/FEATURE_EVALUATION.md). Windows/Docker instructions are not a claim that those environments were run on the current macOS host.

## Configuration before first use

Minimal `.env` values; this example contains no credential:

```dotenv
PMS_HOST=127.0.0.1
PMS_PORT=8000
PMS_ENABLE_LIVE_SCANNER=true
PMS_MAX_MARKETS=40
PMS_MINIMUM_LIQUIDITY=1000
PMS_MINIMUM_VOLUME=0
PMS_DEFAULT_QUANTITY=10
DEEPSEEK_API_KEY=
```

| Setting | Meaning / default |
| --- | --- |
| `PMS_MAX_MARKETS` | Bounded scanner size, 40; allowed 5–500. The catalog is broader than this selection. |
| `PMS_MINIMUM_LIQUIDITY`, `PMS_MINIMUM_VOLUME` | Preselection minimum Gamma liquidity / cumulative volume, 1000 / 0; volume is not 24-hour volume. |
| `PMS_MARKET_REFRESH_SECONDS`, `PMS_REST_REFRESH_SECONDS` | Metadata API verification / book polling waits, 60 / 5 seconds; request duration adds to each cycle. Reading time is separate from source-update time. |
| `PMS_MAX_QUOTE_AGE_SECONDS` | Maximum accepted source-book age, 5 seconds. A new request does not renew a quiet book's source timestamp. |
| `PMS_EXTRA_COST` | Fixed scanner cost assumption, 0.05 pUSD; drawer inspection has its own adjustable value. |
| `PMS_DATABASE_URL` | SQLite database, `sqlite:///data/scanner.db`; translations use separate `data/translations.sqlite3`. |
| `PMS_ENABLE_LIVE_SCANNER` | `false` skips Polymarket background sampling; it does not create sample opportunities. |

Process environment overrides `.env` for startup settings. **Five saved UI parameters override their environment defaults after restart**: minimum net profit, minimum net ROI, quantity, slippage rate, safety rate. Other startup settings require a restart. Save parameters through the UI/API to change an existing database; editing `.env` alone does not replace that saved group.

## Language and your translation API

The language switch changes both the interface and displayed market text. English shows the official source text and does not request LLM translations. The first visit defaults to English; the site remembers an explicit language choice. Chinese requires a configured backend API key, even if some translations were previously cached.

1. Open **Settings → Translation API**.
2. Choose **DeepSeek**, with `https://api.deepseek.com` and the default `deepseek-flash`, or **OpenAI-compatible** with your provider's public HTTPS API base and model name.
3. Enter your **API key** and click **Save API settings**. Saving applies immediately. Configuration status identifies whether the active settings came from the website or the backend environment; the saved key is never returned to the browser.
4. Click **Use Chinese** or the **中文** language button. Interface labels switch locally. Newly visible market titles, events, outcomes and expanded rules are translated in batches and persistently cached. Pending or failed translations keep the source text visible with a status message.

These website save/remove controls require a native local installation. For Docker, use the [environment-based setup above](#docker) and recreate the container after changing `.env`. A remote LAN browser can read configuration status and use an already-configured API, but cannot change credentials through the website.

For a compatible provider, use its **API base URL**, not a complete chat-completions endpoint; for example, a provider that publishes `/v1/chat/completions` normally has a base ending in `/v1`. Only public HTTPS destinations on the default port 443 are accepted; localhost, private networks and other protocols are unsupported. The integration expects the OpenAI-style **Chat Completions** protocol and a model that supports JSON output; providers that expose only other API protocols are unsupported. It does not automatically choose or upgrade models. Saving configuration validates its format; it does not prove that the key, model, balance or provider will work.

Website settings are stored locally in ignored `data/llm-config.json`, with owner-only file permissions on Unix. They take precedence over environment-based DeepSeek settings and survive restart. Leave the key field blank to retain a key only for the same provider and API base; a different destination requires its own key. **Remove saved settings** removes the website override and falls back to any backend environment key, so translation may remain available if one is inherited. Credential changes require a native local loopback connection. Keep this local configuration file private when backing up the project.

Alternatively, set `DEEPSEEK_API_KEY` in the backend environment or ignored project `.env`, then restart. Aliases: `DEEPSEEK_KEY`, `PMS_DEEPSEEK_API_KEY`. `DEEPSEEK_API_BASE` accepts only official `https://api.deepseek.com` or `/v1`. These existing settings also satisfy the Chinese-language requirement. Never put credentials in frontend code, screenshots, logs or GitHub issues.

The DeepSeek preset uses `deepseek-flash` (DeepSeek V4.1 Flash), the cheapest official model checked on 2026-10-02, with thinking disabled. First-time text consumes provider credits; English, fixed interface labels and cached translations do not. A failed integrity check permits at most one corrective retry on the same configured model. Numbers, symbols and URLs are checked, but semantic accuracy still requires reading the source settlement rules. Translation never changes prices, IDs, token/outcome order or calculation inputs. Catalog search uses original title/event text; scanner search also matches already displayed Chinese; CSV always uses source text.

![Translation API settings. The saved key is never displayed.](docs/images/api-settings-en.png)

## B. Verify readiness and explore

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Initial public requests run before readiness, so allow startup time. The initial sample appears first; a larger directory crawl continues in the background.

- [ ] [GET /health](http://127.0.0.1:8000/health) returns `status: "ok"`, `mode: "public-read-only"`. This checks the local database, **not upstream freshness**.
- [ ] [Monitor](http://127.0.0.1:8000/monitor) shows Gamma/CLOB status, REST update time, actual scanner size, WS state, errors and HTTP counters. WS connection alone does not make a calculation current.
- [ ] Catalog reports coverage, revision, update time and selection diagnostics. `capped` means the crawl reached its limit; `partial`/errors mean it was interrupted and may retain an older snapshot.

| Sidebar entry | Do this | Expected behavior |
| --- | --- | --- |
| Markets | Select a category; search original title/event text; change liquidity/sort; paginate; reset | Counts/rows use one directory revision. “Refresh data” reads the server snapshot; it does not force a new whole-site crawl. |
| Strategies | Read a category's signal, required inputs, failure cases and source | Research guidance. No external weather feed, sports odds, calibrated model or live predictive decision is supplied. |
| Open source | Switch high-star / active high-star / all filters; open source links | Stars/maintenance/license/adoption decisions are a dated checked-in snapshot. High stars do not establish profit or current compatibility. |
| Book scanner | Search candidates; open detail; save a qualifying simulation | Only current selected Yes/No markets passing all gates. Auto-refresh preserves search. |
| Monitor | Compare upstream/database state, timestamps, counts and retries | Local health, public connectivity and book freshness are independent. Estimated simulation total is not realized profit. |
| Paper records | Refresh, page through saved observations, export | 100 rows/page; saved estimates do not change with new prices. Empty history is valid. |
| Signal history | Compare first/last seen, max estimate and active/disappeared state | Past signals; status is not permission to execute now. 100 rows/page. |
| Settings | Configure your translation API; edit/save the five scanner parameters | API configuration applies immediately. Scanner parameters persist atomically and clear old candidates until a new book calculation; unsaved/failure states remain explicit. |
| Logs | Select INFO/WARNING/ERROR; refresh | Recent 100 events; visible page polls every 5 seconds. |

Click a directory market to open its drawer. Verify original outcome/token order, adjust per-leg quantity and other cost, inspect all outcome books and expanded rules, then close with Escape. Closed/paused/mapping-changed markets show a pause reason; unknown fees/minimum sizes, old or invalid books also halt useful candidate judgement. Three-or-more outcomes receive descriptive books, not a multi-outcome complete-set strategy. The scanner's separate detail exposes its REST calculation books/time alongside possibly newer WS display books.

Browser polling pauses in hidden tabs; backend polling continues. The drawer/monitor/scanner/logs normally reread every 5 seconds; the catalog page every 15 seconds. Full catalog discovery waits 600 seconds after each crawl and caps at 100 pages of 100 events. One event can contain many markets. Gamma responses may be cached: `metadataAsOf`/verification time means successful reading, not proof of a just-updated source.

### Zero candidates versus a failure

**Zero does not imply a broken service or no platform-wide opportunities.** The selected sample may have no complete positive difference after fees, costs, size and profit/ROI gates. `VALID` can still have a negative net estimate. Unknown fees/minimum size and stale books intentionally block candidates.

Check monitor Gamma/CLOB/error fields, REST source age, actual verified selection, coverage/update time and the detail reason. A successful `/health` with failed upstream fields means the local app works but collection is degraded. A fresh REST response can contain an old quiet source book; it remains `STALE`. A red refresh banner means retained content is an old snapshot. Do not interpret sample counts or WS connectivity as a profit signal.

## C. Save, change parameters, and inspect records

“Save simulation” saves an observation only. The backend rechecks the current scanner candidate under the same refresh lock: matching market/book identities, supported known fees, known minimum size, complete depth, fresh source times, current metadata, minimum executable size and minimum profit/ROI. Missing/expired/nonqualifying snapshots return **409** and do not save a success. Rapid clicks are guarded; intentionally saving another valid observation later is allowed.

If no real candidate appears, verify the empty state and run mocked regression tests in stage E; there is no requirement to fabricate a profitable public trade.

- [ ] For a genuine current candidate, save once; the simulation ID appears in `/paper-trades` and the monitor count increases.
- [ ] Edit a parameter, see “unsaved”, save, then wait for a new successful calculation. Restart restores the saved group. Keep your prior values if merely verifying this workflow.
- [ ] In history/simulations, use next/previous beyond 100 records; empty databases and short pages disable “next”. Records come from the local database, not a wallet.

The five-field parameter API is `GET /api/settings` / `PUT /api/settings`; PUT requires the complete group. ROI/rates are decimal fractions: `0.002` is 0.2%, not 0.002%. These are initial defaults, overridden by valid saved values:

| API field | Default | Allowed range |
| --- | --- | --- |
| `minimum_net_profit` | `0.10` pUSD | 0–1000 |
| `minimum_net_roi` | `0.002` | 0–1 |
| `default_quantity` | `10` shares/leg | >0–100000 |
| `slippage_rate` | `0.001` | 0–0.25 |
| `safety_rate` | `0.001` | 0–0.25 |

API list rows include IDs. Replace `RECORD_ID` with an actual returned ID:

```text
GET /api/paper-trades?limit=100&offset=0
GET /api/paper-trades/RECORD_ID
GET /api/opportunities/history?limit=100&offset=0
GET /api/opportunities/history/RECORD_ID
```

Detail responses include `details.audit`: original mapping, parameters, source/as-of and actual two REST books. Older records may lack those fields. Use [Swagger /docs](http://127.0.0.1:8000/docs) for schemas and requests; unknown IDs return 404 and invalid parameters 422. The drawer's quantity/cost adjustment is inspection-only and does not save global scanner parameters.

## D. Export and retain data

Download through the page buttons or these local routes:

```text
GET /api/exports/opportunities.csv
GET /api/exports/paper-trades.csv
```

Exports stream **all saved rows**, keep stable headers even when empty, use UTF-8 BOM and original market text, and escape formula-looking text. Timestamps carry UTC offsets; the browser formats Asia/Shanghai. Exported estimates are not realized revenue.

With the server stopped, the offline exporter reads the configured database without upstream access:

```sh
python -m scripts.export_sample --output exports/paper-trades.csv
```

The optional `python -m scripts.init_db` prepares schema without changing existing signal status; normal startup does this automatically. `python -m scripts.reset_database` is a destructive SQLite maintenance action: it checks the configured file/service and requires typing `RESET`. It is unnecessary for installation or routine troubleshooting.

Back up `.env` and the entire `data/` directory after stopping the app; they contain local records, saved parameters, translation cache and any saved LLM credential. Store backups privately. Logs are in `logs/`. Git ignores runtime files. Complete raw market-book history, replay/backtesting, automatic retention/deletion and cross-event/platform arbitrage are not implemented.

For an existing checkout, stop the service, back up local data, then:

```sh
git pull --ff-only
python -m pip install -r requirements-lock.txt
python -m app
```

Use the project's activated venv, or Windows `.venv\Scripts\python.exe`. Preserve an existing `.env`; compare new `.env.example` entries instead of overwriting it. If Git reports local conflicts, inspect them; do not reset away your changes. Current schema initialization retains records; future migrations must follow their release notes. `docker compose up --build` rebuilds the image while retaining named volumes.

## E. Development and explicit network verification

After runtime setup, install **Node.js ≥18** and verify `node --version`; no npm packages are needed for the isolated Node VM tests.

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pytest
python scripts/security_scan.py
```

Default pytest excludes live-network tests and mocks paid translation. Without Node, frontend VM cases are explicitly skipped, so a Python-only pass is not the complete suite. On Windows, use `.venv\Scripts\python.exe` for these commands; `lint.bat` / `test.bat` are shortcuts after development dependencies are installed.

Opt in to actual public Gamma/CLOB/geoblock/Market WS connectivity, with no wallet or paid translation request:

```sh
python -m pytest -m live -o addopts="" -s tests/live
```

Equivalent helper: `python -m scripts.smoke_test` (`live_test.bat` on Windows). Network tests depend on the current upstream state and cannot establish guaranteed returns. Report real outcomes in [FEATURE_EVALUATION.md](docs/FEATURE_EVALUATION.md), with synthetic record/candidate cases identified separately.

### Maintainer UI acceptance with isolated synthetic data

To reproduce nonempty records and gate failures without waiting for a real profitable candidate:

```sh
python tests/manual/fixture_server.py --port 8128
```

Open [http://127.0.0.1:8128](http://127.0.0.1:8128). Every market/record is marked **`[TEST]`**. This localhost-only harness uses temporary databases/caches, an empty translation credential, mocked providers and no external market requests; port 8000 is refused. Ctrl+C cleans temporary data. These values never establish a real trading opportunity.

- Market **101** is the sole current synthetic scanner candidate. Save it once, locate the new record and inspect its `details.audit`; it identifies the synthetic source.
- Open **102** unknown fees, **103** unknown minimum size, **104** crossed book, **105** invalid source time/STALE, and **106** currently closed. They must not be offered as executable candidates.
- **107** shows all three outcome books with no binary calculation; **108** permits Up/Down inspection while remaining outside the Yes/No scanner.
- Forty extra directory rows and 101 preloaded simulation/history observations exercise next/previous and CSV beyond one page. Additional fixture scans can create further historical observations; count actual exported/list rows rather than assuming a fixed running total.
- Follow stages B–D, compare desktop/narrow layouts, and record observations in the evaluation. Natural public data and this synthetic harness are separate evidence.

For an offline first-run check in a separate checkout/data directory, set `PMS_ENABLE_LIVE_SCANNER=false`, `PMS_PORT=8127`, leave all translation-key aliases unset/empty, and do not copy a saved `data/llm-config.json`. Run `python -m app`, check `/health` and all navigation routes; markets/candidates remain empty and simulation saving is refused. English works immediately; clicking 中文 must retain English and offer **Configure API**. This tests local setup and the missing-key flow, not Polymarket connectivity.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| Python not found / unsupported | Confirm `python3 --version` or Windows `python --version`; install ≥3.11. macOS can use `PM_PYTHON`. |
| Port already occupied | Stop the intended existing service or choose another `PMS_PORT`; Compose's documented mapping is fixed at host 8000. |
| Startup seems slow / catalog partial | Read terminal/logs and monitor; startup warms public data before readiness, directory discovery is bounded, network calls can retry. |
| `/health` is 503 | Check database path/permissions and disk; this is local storage degradation. Do not delete records as a routine fix. |
| Health 200 but empty scanner | See upstream status, verified selection, thresholds, source age and reason; offline mode and no candidates can both be intentional. |
| 中文 offers Configure API | Save your API in Settings, or configure a backend environment key and restart. Cached Chinese alone does not enable the language. |
| API saving is refused in Docker or over LAN | Use native localhost for website credential changes. Docker reads `.env`; after editing it, recreate the container with `docker compose up -d --force-recreate`. |
| API saved but market text stays English | Read translation status; check the provider's key, model, API base, JSON support and balance. Use Save API settings without restarting, then retry explicitly. |
| `.env` change has no visible effect | Restart startup settings; the five saved parameters intentionally take precedence and must be changed in the UI/API. |
| Missing frontend tests | Install Node and rerun the suite; check the skipped-case summary. |
| Old history remains active / old audit missing | Restart/new scans reconcile state; older records created before audit capture cannot recover absent inputs. |

## License and attribution

MIT. The collection/scanning foundation is adapted from [0106ss/polymarket-market-scanner](https://github.com/0106ss/polymarket-market-scanner), upstream commit `587daca8548f6c737b4d642b49c9f000247361ab`. Original notices remain in [LICENSE](LICENSE); modifications are documented in [UPSTREAM.txt](UPSTREAM.txt). Other repository reviews are references rather than integrated trading SDKs. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [release notes](CHANGELOG.md).
