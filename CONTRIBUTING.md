# Contributing

1. Open an issue describing the change and its public-data scope.
2. Create a focused branch; add meaningful tests for changed behavior.
3. Install `requirements-dev.txt`, then run the checks below (or `lint.bat` / `test.bat` on Windows).
4. Keep live-network tests opt-in. Never add wallet connectivity, wallet secrets, signing, authenticated Polymarket trading, real order submission, transfers, or geographic bypass.
5. Optional DeepSeek credentials belong exclusively on the backend in environment variables or an ignored local `.env`. They may translate public market text only; never expose, log, or commit them. Preserve original data, outcome/token order, settlement identifiers, and Decimal calculations.
6. Submit a pull request using the template and preserve upstream attribution and license notices.

```sh
ruff check .
ruff format --check .
mypy app
python -m pytest
python scripts/security_scan.py
```

Translation defaults to `deepseek-flash` with thinking disabled, batching, persistent caching, and at most one corrective retry on the same model. Verify official availability and prices before changing the cheapest-model default.

By contributing, you agree that your contribution is licensed under MIT. The project is derived from [0106ss/polymarket-market-scanner](https://github.com/0106ss/polymarket-market-scanner); see `UPSTREAM.txt` and `LICENSE`.
