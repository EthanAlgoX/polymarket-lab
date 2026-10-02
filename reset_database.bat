@echo off
setlocal
echo WARNING: This removes data\scanner.db only. Exports and source code are preserved.
set /p confirm=Type RESET to continue:
if /I not "%confirm%"=="RESET" (echo Cancelled. & exit /b 1)
if exist data\scanner.db del /q data\scanner.db
.venv\Scripts\python.exe -m scripts.init_db
