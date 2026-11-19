#!/usr/bin/env bash
# Compile the HE4 (TFHE / Concrete) circuits into .runtime/he4. Idempotent: skips builds that already exist.
# Usage: build_he4_circuits.sh <repo_root> [python]
set -euo pipefail
ROOT="${1:?repo root}"
PY="${2:-/opt/he4-venv/bin/python}"
B="$ROOT/.runtime/he4"
mkdir -p "$B"
cd "$ROOT/agent2"
for spec in "statistics build-statistics-v1" "rules build-rules-difference-v1" "graph build-graph-difference-v1"; do
  set -- $spec
  if [ ! -f "$B/$2/manifest.json" ]; then
    "$PY" -m experiments.he4.build --profile "$1" --output "$B/$2"
  fi
  echo "ready $2"
done
if [ ! -f "$B/build-c3-v1/manifest.json" ]; then
  "$PY" -m experiments.he4.c3_circuit --output "$B/build-c3-v1"
fi
echo "ready build-c3-v1"
ls "$B"
