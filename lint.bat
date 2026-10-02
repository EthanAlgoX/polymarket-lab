@echo off
call .venv\Scripts\activate.bat || exit /b 1
ruff check . || exit /b 1
ruff format --check . || exit /b 1
mypy app || exit /b 1
