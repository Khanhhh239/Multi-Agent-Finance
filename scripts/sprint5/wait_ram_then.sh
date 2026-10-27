#!/usr/bin/env bash
# Wait for the requested free RAM on Windows/Git Bash, then run one command.
set -euo pipefail

if (( $# < 2 )) || ! [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "Usage: bash scripts/sprint5/wait_ram_then.sh <minimum-GiB> <command> [args...]" >&2
  exit 2
fi

minimum_bytes=$(awk -v gib="$1" 'BEGIN { printf "%.0f", gib * 1073741824 }')
shift
while :; do
  available_bytes=$(powershell.exe -NoProfile -Command 'Add-Type -AssemblyName Microsoft.VisualBasic; (New-Object Microsoft.VisualBasic.Devices.ComputerInfo).AvailablePhysicalMemory' | tr -d '\r[:space:]')
  if ! [[ "$available_bytes" =~ ^[0-9]+$ ]]; then
    echo "Cannot read available physical memory" >&2
    exit 1
  fi
  if (( available_bytes >= minimum_bytes )); then
    break
  fi
  echo "Waiting for RAM: ${available_bytes} bytes available, ${minimum_bytes} bytes required" >&2
  sleep 60
done

exec "$@"
