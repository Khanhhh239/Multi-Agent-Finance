"""Package label-checked globals and the frozen empirical partial prior.

Pre-correction globals remain historical evidence in their original directory.
The G0 composition and family configurations stay fixed; no audit/test scores
are consulted to construct this package. Bundle quality requires a new audit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.cash_adapter import LABEL_CONTRACT, fit_partial
from agent1.adaptive.compact_t1 import CompactT1, sha256
from agent1.adaptive.landmark_features import FEATURES, SCHEMA, LandmarkEnsemble
from agent1.adaptive.t1_catalog import CATALOG_VERSION, DEFAULT, GlobalCatalog
from agent1.adaptive.t1_data import risk_rows


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
        print(f"Verified existing catalog {catalog.digest}")
        return
    source = ROOT / "outputs/t1/aligned_cashcalendar_20261113"
    old = ROOT / "outputs/t1/global_local_catalog_v1_20261113"
    contract = json.loads((source / "target_contract.json").read_text(encoding="utf-8"))
    if contract["version"] != LABEL_CONTRACT:
        raise ValueError("Nguồn global chưa sửa nhãn tất toán theo ngày thực thu")
    records = json.loads((source / "candidate_results.json").read_text(encoding="utf-8"))
    sample = json.loads((source / "training_sample.json").read_text(encoding="utf-8"))["sample_sha256"]
    loaded, sources = {}, {}
    for name in ("neural", "lightgbm", "xgboost", "customer"):
        trial = next(r["selected_trial"] for r in records if r["name"] == name)
        path = source / "trials" / f"{name}_{trial}" / "model"
        meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        if meta.get("sample_sha256") != sample:
            raise ValueError("Các global phải dùng chung snapshot, nhãn và trọng số")
        loaded[name] = CompactT1.load(path)
        sources[name] = sha256(path / "metadata.json")
    original = json.loads((old / "default/metadata.json").read_text(encoding="utf-8"))
    loaded["default"] = LandmarkEnsemble(
        [loaded[m["name"]] for m in original["members"]], original["weights"])
    prior_frame, prior_receipts = prepared(source, "validation")
    prior = fit_partial(prior_frame, "2024-06-30", prior=None)
    replay_frame, replay_receipts = prepared(source, "train")
    (x, y, w), replay_evidence = risk_rows(replay_frame, cap=4096)
    output.mkdir(parents=True)
    models = {}
    for name in ("default", "neural", "lightgbm", "xgboost"):
        directory = output / name
        loaded[name].save(directory, dict(available_asof="2024-07-01", label_contract=LABEL_CONTRACT,
                                         target_contract_sha256=sha256(source / "target_contract.json"),
                                         source_metadata_sha256=sources.get(name, sources)))
        models[name] = dict(directory=name, metadata_sha256=sha256(directory / "metadata.json"),
                            available_asof="2024-07-01")
    np.savez_compressed(output / "replay.npz", x=x, y=y, weights=w)
    write(output / "partial.json", prior.record())
    metadata = dict(
        version=CATALOG_VERSION, feature_schema=SCHEMA, features=list(FEATURES), synthetic=True,
        label_contract=LABEL_CONTRACT, models=models, shared_pretraining_sample_sha256=sample,
        replay=dict(file="replay.npz", sha256=sha256(output / "replay.npz"),
                    available_asof="2024-07-01", evidence=replay_evidence, sources=replay_receipts),
        partial=dict(file="partial.json", sha256=sha256(output / "partial.json"),
                     available_asof="2024-07-01", sources=prior_receipts),
        label_audit=dict(source_target_contract=contract, source_metadata_sha256=sources,
                         original_g0_sha256=sha256(old / "default/metadata.json"),
                         original_g0_status="quarantined_pre_cash_calendar_target",
                         g0_composition="same members and weights, corrected-label members"),
        bundle_quality="requires_new_validation_and_audit; historical scores do not certify adapter v2",
    )
    write(output / "catalog.json", metadata)
    catalog = GlobalCatalog(output / "catalog.json")
    print(f"Packaged {len(catalog.models)} label-checked globals and partial prior; {catalog.digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT.parent)
    args = parser.parse_args()
    package(args.output)
