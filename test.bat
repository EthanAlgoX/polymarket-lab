@echo off
setlocal
cd /d "%~dp0" || exit /b 1
call .venv\Scripts\activate.bat || exit /b 1
python -m pytest --cov=app --cov-report=term-missing
exit /b %errorlevel%
