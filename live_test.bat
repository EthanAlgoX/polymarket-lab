@echo off
setlocal
cd /d "%~dp0" || exit /b 1
call .venv\Scripts\activate.bat || exit /b 1
python -m pytest -m live -o addopts="" -s tests\live
exit /b %errorlevel%
