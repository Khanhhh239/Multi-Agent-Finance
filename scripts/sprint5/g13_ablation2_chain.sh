#!/usr/bin/env bash
set -e
# Ablation 2: độ phủ nhãn tối thiểu đủ dùng — điền nhãn thật cho 50% và 80% phần T9 v2 bỏ sót. Tuần tự, nhường RAM.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4
PY=.venv/Scripts/python.exe
W="bash scripts/sprint5/run_after_sprint6.sh"
step(){ echo "=== $(date '+%F %T') $*"; $W "$@"; echo "=== $(date '+%F %T') exit=$?"; }
for v in v2fill50 v2fill80; do
  step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-variant $v
  step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run $v
done
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') ABLATION2 DONE"
