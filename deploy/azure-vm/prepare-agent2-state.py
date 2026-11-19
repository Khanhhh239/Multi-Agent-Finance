#!/usr/bin/env python3
"""Copy the local Agent 2 demo policy and databases into ignored deploy state."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile


REPO = Path(__file__).resolve().parents[2]
FILES = (
    ("agent2/.runtime/platform/snapshots-v2.sqlite3", "agent2/snapshots-v2.sqlite3", "sqlite"),
    ("agent2/.runtime/platform/models-v2.sqlite3", "agent2/models-v2.sqlite3", "sqlite"),
    ("agent2/.runtime/platform/case-queue.sqlite3", "agent2/case-queue.sqlite3", "sqlite"),
    ("agent2/.runtime/platform/remediation.sqlite3", "agent2/remediation.sqlite3", "sqlite"),
    ("agent2/.runtime/platform/analysis-bindings.json", "agent2/analysis-bindings.json", "bindings"),
    ("portal/workspace/agent2_access.json", "portal/agent2_access.json", "access"),
)


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(path, 0o700)


def _copy_sqlite(source: Path, destination: Path, *, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"Refusing to replace existing state file: {destination.name}")
    fd, temporary_name = tempfile.mkstemp(prefix=".agent2-export-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as source_db:
            with sqlite3.connect(temporary) as target_db:
                source_db.backup(target_db)
                target_db.execute("PRAGMA journal_mode=DELETE")
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_json(source: Path, destination: Path, kind: str, *, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"Refusing to replace existing state file: {destination.name}")
    raw = source.read_bytes()
    value = json.loads(raw)
    if kind == "access":
        expected = {"version", "actor_id", "tenant_id", "status", "memberships"}
        if (not isinstance(value, dict) or set(value) != expected or
                value.get("version") != "portal-agent2-access/1.0.0" or
                value.get("status") not in {"active", "revoked"} or
                not isinstance(value.get("memberships"), list)):
            raise ValueError("Agent 2 access policy has an unsupported schema")
    elif kind == "bindings":
        if (not isinstance(value, dict) or set(value) != {"version", "bindings"} or
                not isinstance(value.get("bindings"), list)):
            raise ValueError("Agent 2 analysis bindings have an unsupported schema")
    else:
        raise ValueError("Unknown JSON state file kind")
    temporary = destination.with_name("." + destination.name + ".tmp")
    try:
        temporary.write_bytes(raw)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(output: Path, *, force: bool = False) -> list[str]:
    output = output.resolve()
    copied: list[str] = []
    for relative_source, relative_destination, kind in FILES:
        source = REPO / relative_source
        destination = output / relative_destination
        if not source.is_file():
            raise FileNotFoundError(f"Required local Agent 2 demo state is missing: {relative_source}")
        _private_dir(destination.parent)
        if kind == "sqlite":
            _copy_sqlite(source, destination, force=force)
        else:
            _copy_json(source, destination, kind, force=force)
        copied.append(relative_destination)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO / "deploy" / "azure-vm" / "state")
    parser.add_argument("--force", action="store_true", help="replace the six exported Agent 2 state files")
    args = parser.parse_args()
    try:
        copied = prepare(args.output_dir, force=args.force)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Agent 2 state export failed: {type(error).__name__}")
        return 2
    print("Prepared ignored Agent 2 demo state:")
    for relative in copied:
        print(f"  {relative}")
    print("No HE keys, Portal passwords, or local runtime configuration were copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
