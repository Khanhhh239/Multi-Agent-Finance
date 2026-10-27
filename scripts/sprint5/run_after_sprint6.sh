#!/usr/bin/env bash
set -e
# Chờ hàng đợi sprint6 của agent kia kết thúc rồi mới chạy lệnh (nhường RAM/CPU). Kiểm tra mỗi 3 phút.
while :; do
  if powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/sprint5/other_agent_busy.ps1; then
    echo "$(date +%H:%M) sprint6 queue still running, yielding"; sleep 180
  else
    status=$?
    if (( status == 1 )); then break; fi
    echo "Cannot verify sprint6 queue status (exit=$status)" >&2
    exit "$status"
  fi
done
echo "$(date +%H:%M) sprint6 queue finished"
exec bash scripts/sprint5/wait_ram_then.sh 3.0 "$@"
