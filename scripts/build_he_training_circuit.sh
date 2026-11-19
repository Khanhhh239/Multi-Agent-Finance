#!/usr/bin/env bash
# Compile the encrypted logistic-regression SGD circuit (native Concrete, no verified fallback). Idempotent.
# Usage: build_he_training_circuit.sh <repo_root> <output_dir> [python]
set -euo pipefail
ROOT="${1:?repo root}"
OUT="${2:?output dir}"
PY="${3:-/opt/he4-venv/bin/python}"
if [ -f "$OUT/manifest.json" ] && [ -f "$OUT/server.zip" ]; then
  echo "training circuit already built"; exit 0
fi
mkdir -p "$(dirname "$OUT")"
cd "$ROOT/agent2"
"$PY" -m experiments.he_training.build --output "$OUT"
ls "$OUT"
