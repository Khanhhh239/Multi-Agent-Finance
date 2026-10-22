#!/usr/bin/env bash
# Ablation chẩn đoán G13: nhãn T9 v2 + điền nhãn thật cho phần thiếu. Tuần tự, nhường RAM.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4
PY=.venv/Scripts/python.exe
W="bash scripts/sprint5/run_after_sprint6.sh"
step(){ echo "=== $(date '+%F %T') $*"; $W "$@"; echo "=== $(date '+%F %T') exit=$?"; }
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-variant v2fill
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run v2fill
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') ABLATION DONE"
