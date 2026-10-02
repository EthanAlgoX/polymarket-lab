@echo off
setlocal
if not exist .venv\Scripts\python.exe (echo [ERROR] Run install.bat first. & exit /b 1)
.venv\Scripts\python.exe -c "import socket; s=socket.socket(); r=s.connect_ex(('127.0.0.1',8000)); s.close(); raise SystemExit(1 if r==0 else 0)" || (echo [ERROR] Port 8000 is already in use. & exit /b 1)
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
