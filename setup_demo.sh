#!/usr/bin/env bash
# Dựng toàn bộ môi trường demo Sổ Son trên máy mới (Windows + Git Bash, hoặc Linux). Chạy từ thư mục gốc repo:
#   bash setup_demo.sh
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1

echo "[1/5] Môi trường Python cho bốn agent"
bash setup_env.sh

echo "[2/5] Mô hình Ollama"
for m in qwen3:8b qwen3:4b-instruct-2507-q4_K_M bge-m3 qwen3-embedding:0.6b qwen2.5:0.5b; do ollama pull "$m"; done

echo "[3/5] Agent 3: kho luật (vbpl.vn), vectơ nhúng, mô hình xếp hạng lại"
PY3=$PWD/agent3/.venv/Scripts/python.exe; [ -x "$PY3" ] || PY3=$PWD/agent3/.venv/bin/python
( cd agent3/agent3_tax_compliance
  "$PY3" -m src.lawbase.cli sync
  "$PY3" -m src.lawbase.dense build
  "$PY3" -c "from huggingface_hub import snapshot_download as s; s('AITeamVN/Vietnamese_Reranker', local_dir='models/Vietnamese_Reranker')" )

echo "[4/5] Bộ dữ liệu Minh Phát MPX10 và đồng bộ cấu hình/mô hình 4 Agent"
PY4=agent4/.venv/Scripts/python.exe; [ -x "$PY4" ] || PY4=agent4/.venv/bin/python
"$PY4" data_pipeline/setup_runtime.py --mode full

echo "[5/5] Hoàn tất. Trên Windows chạy: .\run_web.ps1 (hoặc python -X utf8 portal/server.py --start-all) rồi mở http://127.0.0.1:8800"
