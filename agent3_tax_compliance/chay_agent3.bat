@echo off
rem Agent 3 - Tro ly thue: bam dup de chay. Mo trinh duyet tai http://127.0.0.1:8640
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong Python. Chay lan dau:
  echo   python -m venv .venv
  echo   .venv\Scripts\python -m pip install -r requirements.txt
  pause
  exit /b 1
)
where ollama >nul 2>nul
if errorlevel 1 (
  echo [Canh bao] Chua cai Ollama: phan kiem tra hoa don van chay, phan hoi dap luat va AI se dung cau mau.
) else (
  start "" /min ollama serve
)
start "" "http://127.0.0.1:8640"
".venv\Scripts\python.exe" -m src.assistant.web
pause
