@echo off
setlocal
set "PYTHON=%~dp0agent3_tax_compliance\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Agent 3 Python environment was not found.
    exit /b 1
)
"%PYTHON%" -u "%~dp0scripts\invoice_accuracy.py" %*
exit /b %errorlevel%
