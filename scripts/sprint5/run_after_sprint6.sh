#!/usr/bin/env bash
# Chờ hàng đợi sprint6 của agent kia kết thúc rồi mới chạy lệnh (nhường RAM/CPU). Kiểm tra mỗi 3 phút.
while powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sprint5/other_agent_busy.ps1; do
  echo "$(date +%H:%M) sprint6 queue still running, yielding"; sleep 180
done
echo "$(date +%H:%M) sprint6 queue finished"
exec bash scripts/sprint5/wait_ram_then.sh 3.0 "$@"
