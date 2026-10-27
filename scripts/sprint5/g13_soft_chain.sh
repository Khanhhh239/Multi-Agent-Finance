#!/usr/bin/env bash
set -e
# G13 trên tgt5 (niêm phong) với nhãn mềm — đăng ký trước: docs/03_Evaluation/G13_SOFT_LABELS_PREREG.md.
# Chờ chuỗi ablation2 (cùng của tôi) xong để không tranh RAM, rồi: sinh tgt5 → dựng nhánh v2, v2soft → chạy v2, v2soft, oracle → chấm.
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 AGENT1_THREADS=4 OMP_NUM_THREADS=4 G13_WORLD=tgt5 G13_SEED=9505
PY=.venv/Scripts/python.exe
while :; do
  if powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sprint5/other_agent_busy.ps1 -Pattern 'g13_ablation2_chai[n]'; then
    echo "$(date +%H:%M) ablation2 still running"; sleep 120
  else
    status=$?
    if (( status == 1 )); then break; fi
    echo "Cannot verify ablation2 process status (exit=$status)" >&2
    exit "$status"
  fi
done
W="bash scripts/sprint5/run_after_sprint6.sh"
step(){ echo "=== $(date '+%F %T') $*"; $W "$@"; echo "=== $(date '+%F %T') exit=$?"; }
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build-world
G13_BUILD=v2,v2soft step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --build
for v in v2 v2soft oracle; do step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --run $v; done
step $PY -u -W ignore scripts/sprint5/g13_e2e_t9.py --score
echo "=== $(date '+%F %T') SOFT CHAIN DONE"
