# Contributing

1. Open an issue describing the change and its public-data scope.
2. Create a focused branch; add meaningful tests for changed behavior.
3. Follow the README runtime setup, install `requirements-dev.txt` and Node.js ≥18, then run the checks below (or `lint.bat` / `test.bat` on Windows). Node runs the isolated frontend tests without npm dependencies; missing Node causes those cases to skip. CI explicitly installs Node 22.
4. Keep live-network tests opt-in. Never add wallet connectivity, wallet secrets, signing, authenticated Polymarket trading, real order submission, transfers, or geographic bypass.
5. Optional LLM credentials belong exclusively on the backend in environment variables, an ignored local `.env`, or the website's ignored `data/llm-config.json`. They may translate public market text only; never return saved keys to the browser, expose them in source/logs, or commit them. DeepSeek uses its official host; compatible Chat Completions providers require public HTTPS port 443. Preserve original data, outcome/token order, settlement identifiers, and Decimal calculations.
6. Submit a pull request using the template and preserve upstream attribution and license notices.

```sh
ruff check .
ruff format --check .
mypy app
python -m pytest
python scripts/security_scan.py
```

The website defaults to English. Chinese requires a configured user API even when translations are cached; static interface translations are bundled and public market text is translated on demand. Preserve missing-key guidance, language persistence, original-text fallback and configuration revision handling across pages and tabs.

DeepSeek defaults to `deepseek-flash` with thinking disabled, batching, persistent caching, and at most one corrective retry on the same configured model. Verify official availability and prices before changing the cheapest-model default. Compatible providers must support Chat Completions and JSON output; never automatically upgrade the selected model.

Configuration GET responses expose metadata only. PUT/DELETE require native local loopback peers and same-origin requests; never reuse a key when the provider or API base changes. Saving applies without restarting or making a paid test request. Docker uses ignored `.env` configuration because bridge peers cannot change website credentials. Add regression coverage for these boundaries with fake keys and mocked providers; do not spend real translation credits in the default suite. See [configuration contracts](docs/API_REFERENCE.md#translation-api-configuration).

By contributing, you agree that your contribution is licensed under MIT. The project is derived from [0106ss/polymarket-market-scanner](https://github.com/0106ss/polymarket-market-scanner); see `UPSTREAM.txt` and `LICENSE`.
