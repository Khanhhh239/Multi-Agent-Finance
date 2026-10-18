@echo off
cd /d "%~dp0agent3_tax_compliance"
if not defined AGENT3_EXPLANATION_POLICY if exist "configs\explanation\policy.local.json" set "AGENT3_EXPLANATION_POLICY=%~dp0agent3_tax_compliance\configs\explanation\policy.local.json"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See README.md for installation.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m src.local_web
if errorlevel 1 pause
