"""Build the existing Portal assets for a Vercel static deployment.

The generated runtime configuration contains only public routing/capability data.
It must never contain an API key, database URL, bearer token or identity secret.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
_AGENT_IDS = ("agent1", "agent2", "agent3", "agent4")


def _api_base_url() -> str:
    value = os.getenv("MAF_API_BASE_URL", "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise SystemExit("MAF_API_BASE_URL must be an HTTPS origin without query or fragment")
    if parsed.path not in ("", "/"):
        raise SystemExit("MAF_API_BASE_URL must be an origin, not an API path")
    return value


def _enabled_agents() -> list[str]:
    raw = os.getenv("MAF_ENABLED_AGENTS", "agent4")
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values or any(item not in _AGENT_IDS for item in values):
        raise SystemExit("MAF_ENABLED_AGENTS must contain only agent1, agent2, agent3 or agent4")
    return list(dict.fromkeys(values))


def build(output_dir: Path | None = None) -> Path:
    output = (output_dir or ROOT / "build" / "portal-static").resolve()
    if output == ROOT or output == ROOT.parent:
        raise SystemExit("refusing to use a repository root as the static output directory")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    shutil.copytree(ROOT / "portal" / "static", output, dirs_exist_ok=True)
    design_output = output / "design"
    design_output.mkdir()
    for name in ("platform-theme.css", "platform-theme.js"):
        shutil.copy2(ROOT / "design" / name, design_output / name)
    shutil.copytree(ROOT / "design" / "fonts", design_output / "fonts", dirs_exist_ok=True)
    agent4_output = output / "agent4"
    agent4_output.mkdir()
    for name in ("index.html", "chat.css", "chat.js"):
        shutil.copy2(ROOT / "agent4_chat" / name, agent4_output / name)

    runtime = {
        "apiBaseUrl": _api_base_url(),
        "enabledAgents": _enabled_agents(),
    }
    (output / "runtime-config.js").write_text(
        "window.__MAF_RUNTIME_CONFIG__ = Object.freeze("
        + json.dumps(runtime, ensure_ascii=True, separators=(",", ":"))
        + ");\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="explicit generated output directory")
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
