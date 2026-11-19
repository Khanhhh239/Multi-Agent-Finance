#!/usr/bin/env bash
# Dựng môi trường demo lõi Sổ Son trên máy mới (Windows + Git Bash, hoặc Linux).
# Dùng API key cho Agent 3/4; không tải mô hình ngôn ngữ cục bộ.
#   bash setup_demo.sh
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1

echo "[1/5] Môi trường Python cho bốn agent"
bash setup_env.sh

echo "[3/5] Agent 3: kho luật (vbpl.vn)"
PY3=$PWD/agent3/.venv/Scripts/python.exe; [ -x "$PY3" ] || PY3=$PWD/agent3/.venv/bin/python
( cd agent3/agent3_tax_compliance
  "$PY3" -m src.lawbase.cli sync
)

echo "[4/5] Bộ dữ liệu Minh Phát MPX10 và đồng bộ cấu hình/mô hình 4 Agent"
PY4=agent4/.venv/Scripts/python.exe; [ -x "$PY4" ] || PY4=agent4/.venv/bin/python
"$PY4" data_pipeline/setup_runtime.py --mode full

echo "[5/5] Hoàn tất. Trên Windows chạy: .\run_web.ps1 (hoặc python -X utf8 portal/server.py --start-all) rồi mở http://127.0.0.1:8800"
