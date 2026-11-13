"""Hold the old model fixed while comparing its 24-row and census SHAP games."""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import CompactT1, explain_compact, sha256
from experiments.t1_compact.train import write_json
from experiments.t1_compact.train_ensemble import latency_contexts


def audit(source, previous, output, inputs):
    output.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((source / "data_audit.json").read_text(encoding="utf-8"))
    validation = pd.concat(
        [
            pd.read_parquet(
                source / "prepared" / f"{entry['world']}.parquet",
                columns=["world", "origin"],
            )
            for entry in inventory
            if entry["role"] == "validation"
        ],
        ignore_index=True,
    )
    contexts = latency_contexts(source, validation, inputs)
    model = CompactT1.load(previous / "artifact")
    records = []
    for context in contexts:
        opened = context["opened"]
        probabilities = model.distribution(opened)[:, :4].sum(1)
        indices = np.unique(np.linspace(0, len(opened) - 1, 20).round().astype(int))
        for position in indices:
            invoice = opened.iloc[position]
            row = {
                "invoice_id": str(invoice.invoice_id),
                "customer_id": str(invoice.customer_id),
                "payment_probability_4w": float(probabilities[position]),
            }
            measured, timings, references = {}, {}, {}
            for policy in ("legacy24", "representative"):
                target = dict(row)
                started = time.perf_counter()
                reference = explain_compact(
                    [target],
                    opened,
                    [(1.0, model)],
                    context["origin"],
                    background_policy=policy,
                )
                timings[policy] = time.perf_counter() - started
                measured[policy] = target["payment_explanation"]
                references[policy] = reference["count"]
            before = {
                factor["feature"]: factor["contribution_pp"]
                for factor in measured["legacy24"]["factors"]
            }
            after = {
                factor["feature"]: factor["contribution_pp"]
                for factor in measured["representative"]["factors"]
            }
            differences = [abs(after[name] - before[name]) for name in after]
            strongest_before = max(before, key=lambda name: abs(before[name]))
            strongest_after = max(after, key=lambda name: abs(after[name]))
            significant = [name for name in after if abs(after[name]) >= 1.0]
            flips = sum(
                np.sign(after[name]) != np.sign(before[name]) for name in significant
            )
            records.append(
                {
                    "context": context["name"],
                    "invoice_id": str(invoice.invoice_id),
                    "population": len(opened),
                    "legacy_count": references["legacy24"],
                    "representative_count": references["representative"],
                    "max_group_change_pp": max(differences),
                    "mean_group_change_pp": float(np.mean(differences)),
                    "baseline_change_pp": 100
                    * abs(
                        measured["representative"]["baseline_probability"]
                        - measured["legacy24"]["baseline_probability"]
                    ),
                    "strongest_changed": strongest_before != strongest_after,
                    "significant_groups": len(significant),
                    "significant_sign_flips": int(flips),
                    "old_seconds": timings["legacy24"],
                    "representative_seconds": timings["representative"],
                    "representative_audit_samples": measured["representative"][
                        "reference"
                    ]["audit_sample_count"],
                }
            )
        print(
            json.dumps(
                {
                    "event": "background_audit",
                    "context": context["name"],
                    "invoices": len(indices),
                }
            ),
            flush=True,
        )
    frame = pd.DataFrame(records)
    frame.to_csv(output / "shap_background_comparison.csv", index=False)
    report = {
        "model_metadata_sha256": sha256(previous / "artifact/metadata.json"),
        "model_state_features": 10,
        "comparison": "same frozen model and served probabilities; background policy changes",
        "contexts": len(contexts),
        "invoices": len(frame),
        "max_group_change_pp": float(frame.max_group_change_pp.max()),
        "median_max_group_change_pp": float(frame.max_group_change_pp.median()),
        "strongest_group_changed_rows": int(frame.strongest_changed.sum()),
        "significant_sign_flips": int(frame.significant_sign_flips.sum()),
        "significant_groups": int(frame.significant_groups.sum()),
        "old_background_counts": sorted(frame.legacy_count.unique().tolist()),
        "census_background_counts": sorted(
            frame.representative_count.unique().tolist()
        ),
        "all_representative_references_are_census": bool(
            frame.representative_count.eq(frame.population).all()
        ),
        "note": "Sampling sensitivity on the inspected cohorts. Global generalization and causal validity require separate evidence.",
    }
    write_json(output / "shap_background_audit.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=ROOT / "outputs/t1/compact_world_20261112"
    )
    parser.add_argument(
        "--previous",
        type=Path,
        default=ROOT / "outputs/t1/compact_ensemble_20261112_v3",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latency-inputs", type=Path)
    args = parser.parse_args()
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        audit(
            args.source.resolve(),
            args.previous.resolve(),
            args.output.resolve(),
            args.latency_inputs.resolve() if args.latency_inputs else None,
        )
