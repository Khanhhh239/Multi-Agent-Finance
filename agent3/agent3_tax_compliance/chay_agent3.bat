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
".venv\Scripts\python.exe" -c "from src.runtime_config import load_env_file, require_api_keys; load_env_file(); require_api_keys()"
if errorlevel 1 (
  echo [Loi] Agent 3 can AGENT3_LLM_API_KEY va AGENT3_EMBED_API_KEY trong agent3\.env.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8640"
".venv\Scripts\python.exe" -m src.assistant.web
pause
