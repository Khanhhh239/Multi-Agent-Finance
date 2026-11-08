@echo off
cd /d "%~dp0agent3_tax_compliance"
".venv\Scripts\python.exe" -m src.local_web --stop
if errorlevel 1 pause
