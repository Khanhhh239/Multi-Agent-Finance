#!/usr/bin/env bash
# Dựng môi trường Python cho bốn agent (Python 3.12, uv). Chạy một lần từ thư mục gốc.
set -e
cd "$(dirname "$0")"
for a in agent1 agent2 agent3 agent4; do rm -rf "$a/.venv"; uv venv -q -p 3.12 "$a/.venv"; done
uv pip install -q -p agent1/.venv -r agent1/requirements-service.txt &
(cd agent2 && uv pip install -q -p .venv/Scripts/python.exe -r requirements.txt cryptography) &
(uv pip install -q -p agent4/.venv -r agent4/requirements.txt && uv pip install -q -p agent4/.venv -e agent4 --no-deps) &
# Agent 3: lõi + bộ mô hình xếp hạng lại điều luật (torch bản CUDA 12.1)
sed -E '/^(torch|transformers|sentence-transformers|sentencepiece|protobuf|pytest|hypothesis)/d' agent3/agent3_tax_compliance/requirements.txt > /tmp/a3core.txt
(uv pip install -q -p agent3/.venv -r /tmp/a3core.txt \
  && uv pip install -q -p agent3/.venv torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121 \
  && uv pip install -q -p agent3/.venv transformers==4.51.3 sentence-transformers==3.4.1 sentencepiece protobuf huggingface_hub) &
wait
echo ENVS-DONE
