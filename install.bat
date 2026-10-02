@echo off
setlocal
cd /d "%~dp0" || exit /b 1
where python >nul 2>nul || (echo [ERROR] Python 3.11+ not found & exit /b 1)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" || (echo [ERROR] Python 3.11+ required & exit /b 1)
if not exist .venv\Scripts\python.exe (python -m venv .venv || exit /b 1)
.venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" || (echo [ERROR] Existing virtual environment requires Python 3.11+. & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt || exit /b 1
if not exist data mkdir data
if not exist logs mkdir logs
if not exist .env copy .env.example .env >nul
.venv\Scripts\python.exe -m scripts.init_db || exit /b 1
echo [OK] Runtime dependencies and database schema installed. Run run.bat to start.
