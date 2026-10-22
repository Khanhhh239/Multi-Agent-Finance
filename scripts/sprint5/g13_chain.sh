#!/usr/bin/env bash
# Chuỗi G13/tgt3: chờ G17 xong, rồi dựng thế giới quan sát, chạy 3 nhánh T6 tuần tự, chấm chính sách đóng băng.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4
PY=.venv/Scripts/python.exe
while powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'g17_promise_feature[s]' }) { exit 0 } else { exit 1 }"; do echo "$(date +%H:%M) G17 still running"; sleep 120; done
W="bash scripts/sprint5/run_after_sprint6.sh"
step(){ echo "=== $(date '+%F %T') $*"; $W "$@"; echo "=== $(date '+%F %T') exit=$?"; }
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run v2
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run sprint3
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run oracle
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') CHAIN DONE"
