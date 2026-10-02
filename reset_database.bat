@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if not exist .venv\Scripts\python.exe (echo [ERROR] Run install.bat first. & exit /b 1)
.venv\Scripts\python.exe -m scripts.reset_database
exit /b %errorlevel%
