@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if not exist .venv\Scripts\python.exe (echo [ERROR] Run install.bat first. & exit /b 1)
for /f %%P in ('.venv\Scripts\python.exe -c "from app.config import get_settings; print(get_settings().port)"') do set "PM_PORT=%%P"
if not defined PM_PORT (echo [ERROR] Invalid application configuration. & exit /b 1)
.venv\Scripts\python.exe -c "import socket; s=socket.socket(); r=s.connect_ex(('127.0.0.1',int('%PM_PORT%'))); s.close(); raise SystemExit(1 if r==0 else 0)" || (echo [ERROR] Port %PM_PORT% is already in use. & exit /b 1)
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:%PM_PORT%"
.venv\Scripts\python.exe -m app
