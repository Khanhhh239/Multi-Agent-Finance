#!/usr/bin/env bash
set -e
# Một chuỗi duy nhất, tuần tự, nhường RAM (thay cho g13_soft_chain + g13_ablation2_chain, vốn bị chết vì fork/cạn tài nguyên).
# 1) tgt5 + nhãn mềm (docs/03_Evaluation/G13_SOFT_LABELS_PREREG.md)   2) ablation độ phủ nhãn thật 50% / 80% trên tgt3.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4
PY=.venv/Scripts/python.exe
W="bash scripts/sprint5/wait_ram_then.sh 3.0"
step(){ echo "=== $(date '+%F %T') $*"; "$@" ; echo "=== $(date '+%F %T') exit=$?"; }
run(){ echo "=== $(date '+%F %T') [$G13_WORLD] $*"; if $W "$@"; then echo "=== $(date '+%F %T') exit=0"; else status=$?; echo "=== $(date '+%F %T') exit=$status"; exit "$status"; fi; }
export G13_WORLD=tgt5 G13_SEED=9505
[ -f data/synthetic/tgt5/invoices.parquet ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-world
G13_BUILD=v2,v2soft run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build
for v in v2 v2soft oracle; do
  [ -f outputs/g13/e2e_tgt5/$v/t6_shortfall_predictions.csv ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run $v
done
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
export G13_WORLD=tgt3
for v in v2fill50 v2fill80; do
  run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-variant $v
  [ -f outputs/g13/e2e_tgt3/$v/t6_shortfall_predictions.csv ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run $v
done
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') ALL DONE"
