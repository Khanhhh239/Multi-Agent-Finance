"""Descriptive tables for the completed two-model benchmark; no fitting.

Overdue/calendar slices are post-hoc explanations, not selection criteria.
Original prediction, protocol and model artifacts remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/analysis/t1_khanh_vs_v6_20261105"
V6 = ROOT / "outputs/data/t1_competing_v6_20261101"
DEFAULT = ROOT / "outputs/analysis/t1_khanh_vs_v6_detail_20261105"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((BASE / "protocol.lock.json").read_text(encoding="utf-8"))
    verification = json.loads((BASE / "verification.json").read_text(encoding="utf-8"))
    for name, digest in verification["result_sha256"].items():
        if sha(BASE / name) != digest:
            raise ValueError("Original result CSV changed")
    scores = pd.read_csv(BASE / "scores.csv")
    paired = scores.pivot(index=["world", "role", "day", "n"], columns="model", values="paid_brier").reset_index()
    paired["reduction_pct"] = 100 * (1 - paired.v6 / paired.khanh_refit)
    ci = pd.read_csv(BASE / "bootstrap.csv")
    paired = paired.merge(ci[["world", "day", "delta_v6_minus_khanh", "ci_low", "ci_high"]], on=["world", "day"], validate="one_to_one")
    rows, hashes, missing_due = [], {}, 0
    for entry in protocol["entries"]:
        world = entry["name"]
        prediction = BASE / "predictions" / f"{world}.parquet"
        invoice_path = ROOT / "data/synthetic" / world / "invoices.parquet"
        relative = invoice_path.relative_to(ROOT).as_posix()
        if sha(invoice_path) != protocol["protected"][relative]:
            raise ValueError("Original invoice file changed")
        hashes[prediction.relative_to(ROOT).as_posix()] = sha(prediction)
        hashes[relative] = sha(invoice_path)
        frame = pd.read_parquet(prediction)
        invoices = pd.read_parquet(invoice_path, columns=["firm_id", "invoice_id", "due_date"])
        frame = frame.merge(invoices, on=["firm_id", "invoice_id"], how="left", validate="one_to_one", indicator=True)
        if not frame._merge.eq("both").all():
            raise ValueError("Missing invoice during age audit")
        missing_due += int(frame.due_date.isna().sum())
        dpd = (pd.to_datetime(frame.cutoff) - pd.to_datetime(frame.due_date)).dt.days
        frame["overdue_group"] = pd.cut(dpd, [-np.inf, 0, 30, 90, 180, np.inf],
            labels=["not_overdue", "1_30", "31_90", "91_180", "over_180"]).astype("string").fillna("unknown")
        frame["anchor_month"] = pd.to_datetime(frame.cutoff).dt.month.astype(str)
        for dimension in ("overdue_group", "anchor_month"):
            for name, part in frame.groupby(dimension, sort=True):
                result = {"world": world, "role": entry["role"], "dimension": dimension, "group": name, "n": len(part)}
                for model in ("khanh_refit", "v6"):
                    losses = []
                    for day in (28, 91, 365):
                        truth = ((part.cause == 1) & (part.time_days <= day)).to_numpy(float)
                        probability = part[f"{model}_paid_{day}"].to_numpy(float)
                        loss = (probability - truth) ** 2
                        result[f"{model}_brier_{day}"] = float(loss.mean())
                        if day in (28, 91):
                            losses.append(loss)
                        else:
                            result[f"{model}_gap365"] = float((probability - truth).mean())
                    result[f"{model}_primary"] = float(np.mean(losses))
                rows.append(result)
    slices = pd.DataFrame(rows)
    groups = []
    metric_columns = [name for name in slices if name.startswith(("khanh_refit_", "v6_"))]
    for (dimension, group), part in slices.groupby(["dimension", "group"], sort=True):
        result = {"dimension": dimension, "group": group, "n": int(part.n.sum()), "worlds": len(part), "min_world_n": int(part.n.min())}
        result.update({name: float(part[name].mean()) for name in metric_columns})
        result["primary_reduction_pct"] = 100 * (1 - result["v6_primary"] / result["khanh_refit_primary"])
        result["brier365_reduction_pct"] = 100 * (1 - result["v6_brier_365"] / result["khanh_refit_brier_365"])
        groups.append(result)
    aggregate = pd.DataFrame(groups)
    if aggregate.query('dimension=="overdue_group"').n.sum() != 65221:
        raise ValueError("Subgroups do not cover benchmark")
    cash = pd.read_csv(BASE / "cash_scores.csv")
    cash_aggregate = []
    for (model, day), part in cash.groupby(["model", "day"]):
        cash_aggregate.append({"model": model, "day": int(day), "n": int(part.n.sum()),
            "actual_cash_vnd": float(part.actual_cash.sum()),
            **{name: float(np.average(part[name], weights=part.actual_cash)) for name in ("invoice_wape", "firm_aggregate_wape", "aggregate_bias")}})
    sizes = []
    for label, path in (("khanh_refit", BASE / "khanh_refit_model.txt"), ("v6", V6 / "model.txt")):
        booster = lgb.Booster(model_file=str(path))
        sizes.append({"model": label, "file_bytes": path.stat().st_size, "file_mib": path.stat().st_size / 1024**2,
                      "trees": booster.num_trees(), "iterations": booster.current_iteration(), "features": booster.num_feature(), "sha256": sha(path)})
    tables = {"paired_by_world_horizon.csv": paired, "slices_by_world.csv": slices,
              "slices_equal_world.csv": aggregate, "cash_aggregate.csv": pd.DataFrame(cash_aggregate), "model_sizes.csv": pd.DataFrame(sizes)}
    for name, frame in tables.items():
        with (output / name).open("x", encoding="utf-8", newline="") as stream:
            frame.to_csv(stream, index=False, lineterminator="\n")
    if any(sha(ROOT / path) != digest for path, digest in hashes.items()):
        raise ValueError("Inputs changed during descriptive audit")
    summary = {"scope": "post-hoc descriptive analysis of frozen paired predictions; no fit, tuning or reselection",
               "weighting": "equal nonempty Worlds within each slice; cash weighted by actual receipts",
               "missing_due_dates": missing_due, "anchors": 65221,
               "benchmark_protocol_sha256": sha(BASE / "protocol.lock.json"),
               "benchmark_verification_sha256": sha(BASE / "verification.json"),
               "script_sha256": sha(Path(__file__)), "input_sha256": hashes,
               "output_sha256": {name: sha(output / name) for name in tables}}
    with (output / "verification.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(aggregate.query('dimension=="overdue_group"').to_string(index=False))
    print(pd.DataFrame(sizes).to_string(index=False))


if __name__ == "__main__":
    main()
