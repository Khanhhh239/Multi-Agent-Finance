"""Package label-checked globals and the frozen empirical partial prior.

Pre-correction globals remain historical evidence in their original directory.
The G0 composition and family configurations stay fixed; no audit/test scores
are consulted to construct this package. Bundle quality requires a new audit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.cash_adapter import FIT_VERSION, fit_partial
from agent1.adaptive.compact_t1 import sha256
from agent1.adaptive.t1_catalog import CATALOG_VERSION, DEFAULT, GlobalCatalog


def write(path, record):
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def prepared(source, role):
    parts, receipts = [], []
    for path in sorted((source / "prepared").glob(f"compact_*_{role}.parquet")):
        receipt = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if sha256(path) != receipt["sha256"]:
            raise ValueError("Hash snapshot global đã sửa nhãn không khớp")
        frame = pd.read_parquet(path)
        frame["invoice_id"] = frame.world + "/" + frame.firm + "/" + frame.invoice_id
        frame["label_end"] = pd.Timestamp("2023-12-31" if role == "train" else "2024-06-30")
        frame["followup_days"] = np.minimum(91, (frame.label_end - frame.origin).dt.days)
        frame = frame.rename(columns={f"cash_week_{w}": f"cash_{w}" for w in range(1, 14)})
        parts.append(frame)
        receipts.append(dict(file=path.name, sha256=sha256(path), rows=len(frame)))
    if not parts:
        raise ValueError("Thiếu snapshot global đã sửa nhãn")
    return pd.concat(parts, ignore_index=True), receipts


def package(output):
    if output.exists():
        catalog = GlobalCatalog(output / "catalog.json")
        if catalog.metadata["version"] != CATALOG_VERSION:
            raise ValueError("Không ghi đè catalog frozen cũ; chọn thư mục mới cho prior v3")
        print(f"Verified existing catalog {catalog.digest}")
        return
    source = ROOT / "outputs/t1/aligned_cashcalendar_20261113"
    legacy = GlobalCatalog(ROOT / "outputs/t1/settlement_partial_catalog_v2_20261113/catalog.json")
    prior_frame, prior_receipts = prepared(source, "validation")
    if prior_receipts != legacy.metadata["partial"]["sources"]:
        raise ValueError("Migration prior phải dùng đúng snapshot global đã khóa")
    prior = fit_partial(prior_frame, "2024-06-30", prior=None)
    output.mkdir(parents=True)
    # Copy bytes, including metadata: this migration changes only the prior law.
    for name in ("default", "neural", "lightgbm", "xgboost"):
        if legacy.metadata["models"][name]["directory"] != name:
            raise ValueError("Cấu trúc catalog nguồn không hỗ trợ migration này")
        shutil.copytree(legacy.file(name), output / name)
    replay_file = legacy.metadata["replay"]["file"]
    if replay_file != "replay.npz":
        raise ValueError("Tên replay nguồn không hỗ trợ migration này")
    shutil.copy2(legacy.file(replay_file), output / replay_file)
    shutil.copy2(legacy.path, output / "parent_catalog.json")
    write(output / "partial.json", prior.record())
    metadata = deepcopy(legacy.metadata)
    metadata.update(
        version=CATALOG_VERSION,
        compatible_parent=dict(file="parent_catalog.json", sha256=legacy.digest),
        partial=dict(legacy.metadata["partial"], sha256=sha256(output / "partial.json"),
                     fit_version=FIT_VERSION),
        bundle_quality="corrected_prior; requires_new_quality_audit; no inherited_quality_scores",
    )
    write(output / "catalog.json", metadata)
    catalog = GlobalCatalog(output / "catalog.json")
    print(f"Packaged {len(catalog.models)} label-checked globals and partial prior; {catalog.digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT.parent)
    args = parser.parse_args()
    package(args.output)
