"""Load one reviewed synthetic demo phase through the running Agent 1 API.

Files are committed in dependency order, one import at a time (not one atomic
transaction). Retrying after a partial failure keeps original document IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[3]
PHASES = {"history": "01_lich_su", "new": "02_phat_sinh_moi", "schedule": "03_lich_chi"}


def load_phase(client, manifest, pack, phase):
    entries = next(p["files"] for p in manifest["phases"] if p["id"] == PHASES[phase])
    # Verify every source before the first write, never print API credentials.
    for entry in entries:
        payload = (pack / entry["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("Input changed: " + entry["file"])
    workspace = client.get("/v1/workspace")
    workspace.raise_for_status()
    workspace = workspace.json()
    if workspace["company"] != manifest["company"]:
        raise ValueError("Wrong company")
    count = workspace["counts"]["invoices"]
    historical = manifest["history_counts"]["invoices"]
    total = next(e["rows"] for e in manifest["files"] if e["kind"] == "invoices")
    if phase == "history" and count not in (0, historical):
        raise ValueError("History phase must precede new documents; start a fresh run to repeat the demo")
    if phase == "new" and count not in (historical, total):
        raise ValueError("Load history first")
    if phase == "schedule":
        if count != total:
            raise ValueError("Load new documents first")
        pending = client.get("/v1/reconciliation")
        pending.raise_for_status()
        if pending.json()["pending_count"]:
            raise ValueError("Finish reconciliation before loading the schedule")
    for entry in entries:
        path = pack / entry["file"]
        started = time.perf_counter()
        print("CHECK", entry["file"], "...", flush=True)
        response = client.post("/v1/imports/preview", files={"file": (path.name, path.read_bytes())},
            data=dict(kind=entry["kind"], date_format="%Y-%m-%d", number_format="plain",
                      imported_by="Demo Đại Phát: " + PHASES[phase]))
        response.raise_for_status()
        preview = response.json()
        if not preview["can_commit"]:
            raise ValueError((entry["file"], preview.get("errors")))
        print("PREVIEW", entry["file"], preview["rows"], preview.get("counts"),
              "elapsed_seconds=", round(time.perf_counter() - started, 1), flush=True)
        result = client.post("/v1/imports/" + preview["id"] + "/commit")
        result.raise_for_status()
        print("COMMIT", entry["file"], "elapsed_seconds=", round(time.perf_counter() - started, 1), flush=True)
    result = client.get("/v1/workspace")
    result.raise_for_status()
    print(json.dumps(result.json()["counts"], ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=PHASES)
    args = parser.parse_args()
    latest = json.loads((ROOT / ".runtime/agent1-demo/latest.json").read_text(encoding="utf-8"))
    path = Path(latest["manifest"])
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("synthetic") or latest["company"] != "DEMO_DAIPHAT":
        raise ValueError("This loader is restricted to the fictional demo")
    key = (Path(latest["keys"]) / "api-token.txt").read_text(encoding="utf-8").strip()
    with httpx.Client(base_url=latest["agent_url"], headers={"Authorization": "Bearer " + key},
                      timeout=600, trust_env=False) as client:
        load_phase(client, manifest, path.parent, args.phase)


if __name__ == "__main__":
    main()
