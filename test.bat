@echo off
call .venv\Scripts\activate.bat || exit /b 1
python -m pytest --cov=app --cov-report=term-missing
exit /b %errorlevel%
