@echo off
cd /d "%~dp0agent3_tax_compliance"
set "AGENT3_OCR_PROFILE=ppocrv6_vietocr_coverage"
set "CAPTURE_RENDER_DPI=200"
if not defined AGENT3_EXPLANATION_POLICY if exist "configs\explanation\policy.local.json" set "AGENT3_EXPLANATION_POLICY=%~dp0agent3_tax_compliance\configs\explanation\policy.local.json"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m src.local_web --port 8010 --database "%~dp0agent3_tax_compliance\data\ocr_lab\capture.sqlite3"
if errorlevel 1 pause
