# Polymarket Lab

[简体中文](README_CN.md)

A local Polymarket research workspace for browsing open markets by category, inspecting orderbook depth, and evaluating fee-aware paper opportunities. The catalog, strategy references, scanner, monitor, history, and settings share a responsive sidebar.

Data comes directly from official Polymarket APIs; no website HTML scraping or third-party quote service is used. The application cannot connect wallets, sign transactions, submit orders, or move funds. Estimates are public-snapshot simulations, not completed trades or guaranteed returns.

## Quick start

Requires Python 3.11 or newer; Python 3.12 is recommended.

```sh
git clone https://github.com/EthanAlgoX/polymarket-lab.git
cd polymarket-lab
```

On macOS:

```sh
./start-local.command
```

The launcher creates `.venv` and installs locked dependencies on first use. If a translation key was not inherited, it loads the user's interactive zsh environment.

On Linux, or for manual setup:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Initial discovery runs in the background. Windows scripts (`install.bat`, `run.bat`) and `docker compose up --build` are also included.

## Data scope

- Gamma `/events/keyset` supplies popular, new, and category samples, followed by at most 100 pages of 100 events per pass. Discovery repeats approximately ten minutes after each pass. The UI reports coverage and failures; the cap does not establish a complete global inventory.
- Categories cover sports, weather, crypto, economy/finance, politics, and other markets. Labels, volume, and liquidity help research screening; they are not profit signals.
- The scanner selects a bounded number of binary Yes/No markets (`PMS_MAX_MARKETS`). CLOB `/books` refreshes every five seconds by default. The public Market WebSocket subscribes to selected tokens, but calculations use REST snapshots.
- Details preserve outcome/token ordering, including team-name and Up/Down binary outcomes. `Decimal` calculations check depth, fees, quote freshness, minimum size, and buffers. Unknown or unsupported fees cannot produce valid opportunities.
- Paper records, history, and CSV exports are local. Strategy pages describe research candidates; external weather feeds, sports odds, calibrated prediction models, and real trading are not implemented.

## Optional Chinese translation

Chinese display is the default; switching to English restores official text. With DeepSeek configured, new or changed visible titles, events, outcomes, and expanded rules translate automatically.

Set `DEEPSEEK_API_KEY` in the server environment or ignored local `.env`. Aliases `DEEPSEEK_KEY` and `PMS_DEEPSEEK_API_KEY` are accepted. Optional `DEEPSEEK_API_BASE` accepts only official `https://api.deepseek.com` or `https://api.deepseek.com/v1`.

The model is `deepseek-flash` (DeepSeek V4.1 Flash), the cheapest official API model verified on 2026-10-02, with thinking disabled. Visible text is batched and persisted in `data/translations.sqlite3`. Bounded corrective retries use the same model; no automatic upgrade to a more expensive model occurs. New text consumes provider credits. Missing credentials or translation failures leave the original text visible with an explicit status.

Keys stay on the backend. Translation changes display text only; calculations, prices, IDs, and outcome/token ordering retain original data. Consult the English rules for settlement. Search and CSV exports currently use original text.

## Configuration and validation

Application settings use the `PMS_` prefix; see `.env.example` and the settings page. Runtime files live in `data/` and `logs/`. Do not commit credentials, `.venv`, databases, logs, exports, or caches.

```sh
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy app
python -m pytest
python scripts/security_scan.py
```

Default tests use mocks and exclude live tests. `python -m pytest -m live` explicitly verifies public Polymarket connectivity. Tests do not require wallets or paid translation calls.

## License and attribution

MIT licensed. The collection/scanning foundation is adapted from [0106ss/polymarket-market-scanner](https://github.com/0106ss/polymarket-market-scanner), commit `587daca8548f6c737b4d642b49c9f000247361ab`. Original copyright and licensing are retained in [LICENSE](LICENSE); changes are recorded in [UPSTREAM.txt](UPSTREAM.txt). Other projects listed in the research UI are references, not integrated code.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
