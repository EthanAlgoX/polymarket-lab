@echo off
setlocal
where python >nul 2>nul || (echo [ERROR] Python 3.11+ not found & exit /b 1)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" || (echo [ERROR] Python 3.11+ required & exit /b 1)
if not exist .venv python -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat || exit /b 1
python -m pip install --upgrade pip --quiet || exit /b 1
python -m pip install --quiet -r requirements-dev.txt || exit /b 1
if not exist data mkdir data
if not exist logs mkdir logs
if not exist .env copy .env.example .env >nul
python -m scripts.init_db || exit /b 1
python -m pytest -m "not live" || exit /b 1
echo [OK] Installation and base tests completed.
