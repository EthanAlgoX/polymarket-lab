@echo off
call .venv\Scripts\activate.bat || exit /b 1
python -m pytest -m live -o addopts="" -s tests\live
exit /b %errorlevel%
