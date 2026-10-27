#!/usr/bin/env bash
set -e
# Lặp lại nhánh T9 v2 + nhãn mềm trên tgt3 (KHÔNG niêm phong: đã dùng cho G13 trước đó) để kiểm tra kết quả tgt5 không phải ngẫu nhiên một bộ đích.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4 G13_WORLD=tgt3
PY=.venv/Scripts/python.exe
W="bash scripts/sprint5/wait_ram_then.sh 3.0"
run(){ echo "=== $(date '+%F %T') [$G13_WORLD] $*"; if $W "$@"; then echo "=== $(date '+%F %T') exit=0"; else status=$?; echo "=== $(date '+%F %T') exit=$status"; exit "$status"; fi; }
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-variant v2soft
[ -f outputs/g13/e2e_tgt3/v2soft/t6_shortfall_predictions.csv ] || run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run v2soft
run $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') REPL DONE"
