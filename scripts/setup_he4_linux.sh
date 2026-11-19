#!/usr/bin/env bash
# Create /opt/he4-venv (Python 3.12 + torch CPU + Concrete-Python 2.11.0) inside the WSL distro. Idempotent. Run as root.
# Usage: setup_he4_linux.sh <repo_root>
set -euo pipefail
ROOT="${1:?repo root}"
VENV=/opt/he4-venv
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import concrete.fhe, torch" 2>/dev/null; then
  echo "he4-venv already ready"; exit 0
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip build-essential libgmp-dev >/dev/null
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
"$VENV/bin/pip" install -q -r "$ROOT/agent2/requirements-he4-linux.txt" --extra-index-url https://download.pytorch.org/whl/cpu
"$VENV/bin/python" -c "import concrete.fhe as f, torch; print('concrete', f.__version__ if hasattr(f,'__version__') else 'ok')"
