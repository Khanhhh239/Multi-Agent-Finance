#!/usr/bin/env bash
# Dựng môi trường Python lõi cho bốn agent (Python 3.12, uv). Chạy một lần từ thư mục gốc.
# Agent 3 dùng API key của Groq/OpenRouter/Cohere cho các chức năng AI.
set -e
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

venv_python() {
  if [ -x "$1/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT_DIR/$1/.venv/bin/python"
  else
    printf '%s\n' "$ROOT_DIR/$1/.venv/Scripts/python.exe"
  fi
}

for a in agent1 agent2 agent3 agent4; do rm -rf "$a/.venv"; uv venv -q -p 3.12 "$a/.venv"; done
A1_PY="$(venv_python agent1)"
A2_PY="$(venv_python agent2)"
A3_PY="$(venv_python agent3)"
A4_PY="$(venv_python agent4)"

(cd agent1 && uv pip install -q --python "$A1_PY" -r requirements-service.txt) &
(cd agent2 && uv pip install -q --python "$A2_PY" -r requirements.txt cryptography) &
(cd agent4 && uv pip install -q --python "$A4_PY" -r requirements.txt \
  && uv pip install -q --python "$A4_PY" -e . --no-deps) &
(cd agent3/agent3_tax_compliance && uv pip install -q --python "$A3_PY" -r requirements.txt) &
wait

echo ENVS-DONE
