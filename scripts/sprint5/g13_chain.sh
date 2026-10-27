#!/usr/bin/env bash
set -e
# Chuỗi G13/tgt3: chờ G17 xong, rồi dựng thế giới quan sát, chạy 3 nhánh T6 tuần tự, chấm chính sách đóng băng.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4
PY=.venv/Scripts/python.exe
while :; do
  if powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sprint5/other_agent_busy.ps1 -Pattern 'g17_promise_feature[s]'; then
    echo "$(date +%H:%M) G17 still running"; sleep 120
  else
    status=$?
    if (( status == 1 )); then break; fi
    echo "Cannot verify G17 process status (exit=$status)" >&2
    exit "$status"
  fi
done
W="bash scripts/sprint5/run_after_sprint6.sh"
step(){ echo "=== $(date '+%F %T') $*"; $W "$@"; echo "=== $(date '+%F %T') exit=$?"; }
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run v2
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run sprint3
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run oracle
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') CHAIN DONE"
