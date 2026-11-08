@echo off
setlocal
cd /d "%~dp0"
if not exist "agent3_tax_compliance\.venv\Scripts\python.exe" (
  echo Missing app Python environment. See README.md.
  exit /b 1
)
if "%~1"=="" (
  "agent3_tax_compliance\.venv\Scripts\python.exe" scripts\invoice_test.py run
) else (
  "agent3_tax_compliance\.venv\Scripts\python.exe" scripts\invoice_test.py %*
)
set "invoice_test_exit=%errorlevel%"
if not "%invoice_test_exit%"=="0" echo Command returned %invoice_test_exit%. Check output above.
exit /b %invoice_test_exit%
