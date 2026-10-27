#!/usr/bin/env bash
set -e
# B1 — G13 với hàng chờ duyệt (docs/03_Evaluation/G13_REVIEW_QUEUE_PREREG.md). Tuần tự, nhường RAM.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4
PY=.venv/Scripts/python.exe
W="bash scripts/sprint5/wait_ram_then.sh 3.0"
run(){ echo "=== $(date '+%F %T') [$G13_WORLD] $*"; if $W "$@"; then echo "=== $(date '+%F %T') exit=0"; else status=$?; echo "=== $(date '+%F %T') exit=$status"; exit "$status"; fi; }
export G13_WORLD=tgt6 G13_SEED=6606
[ -f data/synthetic/tgt6/invoices.parquet ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-world
G13_BUILD=v2soft,v2rev2,v2rev5 run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build
for v in v2rev5 v2soft v2rev2 oracle; do
  [ -f outputs/g13/e2e_tgt6/$v/t6_shortfall_predictions.csv ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run $v
done
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
export G13_WORLD=tgt3
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-variant v2rev5
[ -f outputs/g13/e2e_tgt3/v2rev5/t6_shortfall_predictions.csv ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run v2rev5
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') REVIEW CHAIN DONE"
