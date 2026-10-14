@echo off
cd /d "%~dp0agent3_tax_compliance"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See README.md for installation.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m src.local_web
if errorlevel 1 pause
