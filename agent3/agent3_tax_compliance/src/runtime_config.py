"""Small runtime environment loader shared by Agent 3's model adapters.

Agent 3 is also runnable directly from its project folder, so it cannot rely on
the Portal being the process that loaded ``.env``.  This intentionally supports
only the simple KEY=value format used by the project and never logs values.
"""

from __future__ import annotations

import os
from pathlib import Path


# The executable package lives in agent3/agent3_tax_compliance/src; the project keeps
# one ignored .env at the repository root (template: .env.example). In the VM image
# that file does not exist and the variables come from the container environment.
ENV_FILE = Path(__file__).resolve().parents[3] / '.env'


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not key or not key.replace('_', 'a').isalnum() or key[0].isdigit():
            continue
        # The shared file also holds Agent 4 keys and VM settings; Agent 3 takes only its own.
        if not key.startswith('AGENT3_'):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # Explicit process variables take precedence over the ignored .env file.
        os.environ.setdefault(key, value)


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def require_api_keys() -> None:
    """Fail fast when Agent 3 is started without authenticated providers."""
    missing = [
        name for name in ('AGENT3_LLM_API_KEY', 'AGENT3_EMBED_API_KEY')
        if not (env(name) or env('AGENT3_API_KEY'))
    ]
    if missing:
        raise RuntimeError('Agent 3 requires API keys: ' + ', '.join(missing))


# Direct CLI entrypoints (law evaluation, embedding build, and the web) all
# use the same ignored credentials file; explicit process variables win.
load_env_file()
