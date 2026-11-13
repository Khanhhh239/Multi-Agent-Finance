"""Run one periodic T1 cycle against the same encrypted tenant store as /v1.

Invoke daily from a scheduler; the persisted policy interval prevents duplicate
training. No synthetic data is generated and no HTTP server needs to be running.
"""

import argparse
import json
import os
from pathlib import Path

from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1.adaptive.t1_update import UpdatePolicy

from agent1_service.store import Store
from agent1_service.workspace.t1_lifecycle import now, run_cycle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--firm", required=True)
    parser.add_argument("--state", default=os.environ.get("AGENT1_STATE_DIR", ".state"))
    parser.add_argument("--cutoff", default=now().date().isoformat())
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--interval-days", type=int, default=28)
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--payments-complete", action="store_true", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    directory = Path(args.state)
    key_dir = Path(
        os.environ.get("AGENT1_KEY_DIR")
        or directory.parent / (directory.name + "-keys")
    )
    key = key_dir / "encryption.key"
    if not key.exists():
        key = directory / "encryption.key"
    if not key.exists() or not (directory / "agent1.db").is_file():
        raise ValueError("Kho dữ liệu doanh nghiệp chưa được khởi tạo")
    store = Store(directory / "agent1.db", key.read_bytes())
    try:
        result = run_cycle(
            store,
            args.firm,
            args.cutoff,
            payments_complete=args.payments_complete,
            catalog=GlobalCatalog(args.catalog),
            policy=UpdatePolicy(
                interval_days=args.interval_days, lookback_days=args.lookback_days
            ),
            force=args.force,
            progress=lambda message: print(message, flush=True),
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    finally:
        store.connection.close()


if __name__ == "__main__":
    main()
