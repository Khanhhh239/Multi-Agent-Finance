"""Export the v5 first-event table and risk-set row counts for audit."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from agent1.data.world_manifest import sha256_file
from agent1.paths import ROOT
from experiments.t1_competing_v5.core import OPEN, PAID, WRITEOFF
from experiments.t1_competing_v5.run import OUTPUT, PROTOCOL_PATH, TRAIN_META, read_inputs, world_snapshots


def risk_weeks(frame: pd.DataFrame, horizon: int) -> np.ndarray:
    """Count complete weeks with invoice open at start, including event week."""
    time = frame.time_days.to_numpy(dtype=int)
    obs = frame.obs_days.to_numpy(dtype=int)
    result = np.minimum.reduce((np.full(len(frame), horizon), obs // 7,
                                (time + 6) // 7))
    return result.astype(np.int16)


def main() -> None:
    protocol, cohort, old_meta, _ = read_inputs()
    metadata = json.loads(TRAIN_META.read_text(encoding="utf-8"))
    if metadata["protocol_sha256"] != sha256_file(PROTOCOL_PATH) or \
            metadata["cohort_sha256"] != old_meta["cohort_sha256"]:
        raise ValueError("Event audit differs from locked v5 protocol/cohort")
    train_cutoffs = pd.date_range(protocol["train_first_cutoff"], protocol["train_last_cutoff"],
                                  freq=f'{protocol["train_stride_days"]}D')
    eval_cutoffs = pd.date_range(protocol["eval_first_cutoff"], protocol["eval_last_cutoff"],
                                 freq=f'{protocol["eval_stride_days"]}D')
    eval_cutoffs = eval_cutoffs[(pd.Timestamp(protocol["eval_label_end"]) - eval_cutoffs).days >= 371]
    frames = []
    for index, entry in enumerate(cohort["worlds"]):
        role, world = entry["role"], entry["name"]
        cutoffs = train_cutoffs if role == "train" else eval_cutoffs
        label_end = protocol["train_label_end"] if role == "train" else protocol["eval_label_end"]
        frame = world_snapshots(world, cutoffs, label_end)
        if role == "train":
            cap = protocol["max_train_snapshots_per_world"]
            if len(frame) > cap:
                frame = frame.sample(cap, random_state=protocol["train_seed"] + index)
        else:
            frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id")
        frame = frame.reset_index(drop=True)
        frame["risk_weeks"] = risk_weeks(frame, protocol["horizon_weeks"])
        frame["role"] = role
        frame["world"] = world
        frames.append(frame[["world", "role", "invoice_id", "cutoff", "closure_type",
                             "label_date", "writeoff_date", "time_days", "obs_days",
                             "cause", "risk_weeks"]])
        print(f"events {world}: {len(frame):,}", flush=True)
    result = pd.concat(frames, ignore_index=True)
    train = result[result.role == "train"]
    eval_rows = result[result.role != "train"]
    if len(train) != metadata["n_snapshots"] or \
            int(train.risk_weeks.sum()) != metadata["n_weekly_rows"]:
        raise ValueError("Materialized training risk set differs from model training")
    if eval_rows.duplicated(["world", "invoice_id"]).any():
        raise ValueError("Evaluation anchor has duplicate invoice")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "event_table.parquet"
    result.to_parquet(path, index=False)
    summary = {"event_table_sha256": sha256_file(path), "train_snapshots": len(train),
               "eval_invoices": len(eval_rows), "weekly_risk_rows": int(train.risk_weeks.sum()),
               "train_first_event_counts": {name: int((train.cause == value).sum())
                                            for name, value in (("open_censored", OPEN),
                                                                ("paid", PAID), ("writeoff", WRITEOFF))},
               "eval_first_event_counts": {name: int((eval_rows.cause == value).sum())
                                           for name, value in (("open_censored", OPEN),
                                                               ("paid", PAID), ("writeoff", WRITEOFF))},
               "code_sha256": sha256_file(__file__)}
    (OUTPUT / "event_table_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
