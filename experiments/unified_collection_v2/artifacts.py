"""Verify historical benchmark code from its snapshot, without loading it.

The live package can be refactored while the original measurements, model
weights and source snapshot remain immutable. A snapshot is evidence only;
it is never imported or extracted into the active package.
"""
import hashlib
import json
from pathlib import Path
import zipfile

from agent1.data.world_manifest import sha256_file
from agent1.paths import ROOT


def verify_source_snapshot(directory):
    directory = Path(directory)
    expected = json.loads((directory/"source_hashes.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(directory/"source_snapshot.zip") as snapshot:
        names = snapshot.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("Historical snapshot does not match its source inventory")
        for name, digest in expected.items():
            if hashlib.sha256(snapshot.read(name)).hexdigest() != digest:
                raise ValueError(f"Historical source snapshot changed: {name}")
    active_matches = all((ROOT/name).is_file() and sha256_file(ROOT/name)==digest
                         for name,digest in expected.items())
    return {"frozen_source_snapshot_verified":True, "snapshot_files":len(expected),
            "active_source_matches_snapshot":active_matches}


def verify_saved_run(directory):
    directory = Path(directory).resolve()
    result = verify_source_snapshot(directory)
    maintenance = ROOT/"outputs/maintenance/unified_v1_removal_20261104.json"
    if not maintenance.exists() or not directory.is_relative_to(ROOT):
        raise ValueError("No preservation inventory for this historical run")
    record = json.loads(maintenance.read_text(encoding="utf-8"))
    prefix = directory.relative_to(ROOT).as_posix()+"/"
    files = {name:digest for name,digest in record["preserved_files_sha256"].items() if name.startswith(prefix)}
    if not files:
        raise ValueError("Historical run missing from preservation inventory")
    actual = {f.relative_to(ROOT).as_posix() for f in directory.rglob("*")
              if f.is_file() and "__pycache__" not in f.parts}
    if actual != set(files):
        raise ValueError("Historical artifact inventory changed")
    for name,digest in files.items():
        if sha256_file(ROOT/name)!=digest:
            raise ValueError(f"Historical artifact changed: {name}")
    result.update(artifact_files_verified=len(files),
                  decision=json.loads((directory/"decision.json").read_text(encoding="utf-8")),
                  scope="read saved results only; no training or new holdout forecasts")
    return result
