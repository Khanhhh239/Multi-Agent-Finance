"""Fetch pinned public Kaggle BenchRec v3; verify archive and preserve immutable raw."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from t0.benchrec import verified_path
from t0.data import write_json

URL = "https://www.kaggle.com/api/v1/datasets/download/benchmarkteam/benchrec-real-world-cash-reconciliation-dataset?datasetVersionNumber=3"
ARCHIVE_HASH = "46d6851a47f1888a7295ac5f7d49295f845b5041ddd18965fef7b79be1b86b4b"
EXPECTED = {
    "BenchRec_cash_v1.0_train.csv": "a7d66dc4a2fcf65abc1047d9f60905dfd248bad9db4c34920c3a9c86e6fadefb",
    "BenchRec_cash_v1.0_eval.csv": "2b1d2f734420d92c12b563d8f9a281608f9a50a8305369ac41913aa39b508bdf",
    "BenchRec_cash_v1.0_solution.csv": "1cb0fe95563b2c191fbfafe206e6fb97eb7844a486dbc3a1638c1c7ff2362477",
    "MatcherByChatGPT_submission.csv": "ca74a5f846f681eb74b0476505d03b0ee2c8a7eb743f83ea990414d3f2fe7a8d",
}


def checked_members(payload, archive_hash=ARCHIVE_HASH, expected=None):
    expected = EXPECTED if expected is None else expected
    if hashlib.sha256(payload).hexdigest() != archive_hash:
        raise ValueError("Pinned archive hash differs; do not silently accept another snapshot")
    with ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if len(infos) != len(expected) or {item.filename for item in infos} != set(expected):
            raise ValueError("Unexpected/duplicate ZIP members")
        if sum(item.file_size for item in infos) > 150_000_000:
            raise ValueError("Uncompressed archive exceeds limit")
        result = {}
        for item in infos:
            if Path(item.filename).name != item.filename or "\\" in item.filename:
                raise ValueError("Unsafe ZIP member")
            value = archive.read(item)
            if hashlib.sha256(value).hexdigest() != expected[item.filename]:
                raise ValueError("Pinned member hash differs")
            result[item.filename] = value
        return result


def download(directory):
    directory = Path(directory)
    if (directory / "source_manifest.json").exists():
        for filename, expected_hash in EXPECTED.items():
            path = verified_path(directory, filename)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError("Cached raw differs from pinned v3")
        payload = (directory / "dataset.zip").read_bytes()
        if hashlib.sha256(payload).hexdigest() != ARCHIVE_HASH:
            raise ValueError("Cached archive missing or changed")
        return "verified_cached"
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Nonempty raw directory without manifest; choose a fresh output")
    with urlopen(Request(URL, headers={"User-Agent": "T0-Research/1.0"}), timeout=60) as response:
        payload = response.read(40_000_001)
    if len(payload) > 40_000_000:
        raise ValueError("Archive exceeds download limit")
    members = checked_members(payload)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dataset.zip").write_bytes(payload)
    entries = []
    for name, value in members.items():
        (directory / name).write_bytes(value)
        entries.append({"file": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()})
    write_json(directory / "source_manifest.json", {
        "source_id": "benchrec-kaggle-v3", "version": 3, "download_status": "downloaded",
        "use_policy": "inspection_only_excluded_from_matching", "url": URL,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(), "files": entries,
        "archive_sha256": ARCHIVE_HASH, "license": "Dataset card states CC BY 4.0; publisher claim",
        "scope": "GL-bank benchmark adapter only; not input to the positive invoice matcher"})
    return "downloaded_verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/T0/raw/benchrec_kaggle/2026-10-19-v3")
    args = parser.parse_args()
    print(json.dumps({"status": download(args.output), "output": str(args.output)}))


if __name__ == "__main__":
    main()
