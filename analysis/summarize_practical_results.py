"""Build descriptive tables only after locked fresh evaluation; never select."""
from pathlib import Path
import argparse
import json
import zipfile
from xml.etree import ElementTree

import pandas as pd

from experiments.t1_v6_practical.run import ROOT, ORIGINAL, digest, json_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "outputs/data/t1_v6_practical_20261105_r2")
    args = parser.parse_args()
    out = args.directory.resolve()
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    selection = json.loads((out / "final_selection.lock.json").read_text(encoding="utf-8"))
    initial = json.loads((out / "protocol.primary_fit.json").read_text(encoding="utf-8"))
    current = json.loads((out / "protocol.lock.json").read_text(encoding="utf-8"))
    if initial["fresh_worlds"] != current["fresh_worlds"] or summary["selected"] != selection["selected"] or summary["fresh_selection_performed"]:
        raise ValueError("Fresh design or frozen source selection changed")
    receipt_hash = digest(out / "final_selection.lock.json")
    for i in range(4):
        receipt = json.loads((out / f"fresh_generation_receipt_{i}.json").read_text(encoding="utf-8"))
        if receipt["selection_lock_sha256"] != receipt_hash:
            raise ValueError("Fresh generation used a different selection lock")
    if any(digest(out / "models" / f"{name}.txt") != sha for name, sha in selection["models_sha256"].items()):
        raise ValueError("Model changed after source freeze")
    def read(name):
        return pd.read_csv(out / name, float_precision="round_trip")
    source, fresh = read("all_source_scores.csv"), read("fresh_scores.csv")
    def model_table(table):
        means = table[table.day.eq(365)].groupby("model", sort=False)[["four_state_brier", "writeoff_brier"]].mean()
        base = means.loc["v6"]
        rows = []
        for name, row in means.iterrows():
            metadata = json.loads((out / "models" / f"{name}.json").read_text(encoding="utf-8"))
            rows.append({"model": name, "fit_n": metadata["n_snapshots"],
                         "joint_brier365": float(row.four_state_brier), "writeoff_brier365": float(row.writeoff_brier),
                         "joint_improvement_pct": float(100 * (1-row.four_state_brier/base.four_state_brier)),
                         "writeoff_improvement_pct": float(100 * (1-row.writeoff_brier/base.writeoff_brier))})
        return rows
    chosen = summary["selected"]
    world_rows = []
    for world, part in fresh[fresh.model.eq(chosen)].groupby("world", sort=False):
        part = part.set_index("day")
        b = fresh[fresh.model.eq("v6") & fresh.world.eq(world)].set_index("day")
        long = part.loc[365]
        world_rows.append({"world": world, "n": int(long.n), "joint_brier365_v6": float(b.loc[365, "four_state_brier"]),
                           "joint_brier365_selected": float(long.four_state_brier),
                           "actual_writeoff365_pct": float(long.actual_writeoff * 100),
                           "pred_writeoff365_pct": float(long.pred_writeoff * 100), "writeoff_gap365_pp": float(long.writeoff_gap * 100),
                           "max_paid_ece": float(part.paid_ece.max()),
                           "max_short_paid_brier_ratio": float((part.loc[[28, 91], "paid_brier"] / b.loc[[28, 91], "paid_brier"]).max())})
    support = []
    for label, name in (("primary", "primary_source_support.csv"), ("augmented", "augmented_source_support.csv")):
        table = read(name)
        for row in table[table.feature.isin(["c_tenure_days", "c_n_hist", "f_n_hist"])].to_dict("records"):
            support.append({"fit": label, "feature": row["feature"], "train_max": row["train_max"],
                            "source_outside_range_pct": 100*row["outside_train_range_fraction"]})
    mask = read("industry_missing_sensitivity.csv")
    tables = {"source_models": model_table(source), "fresh_models": model_table(fresh), "fresh_worlds_selected": world_rows,
              "source_support": support,
              "fresh_bootstrap365": read("fresh_bootstrap.csv").query("day == 365").to_dict("records"),
              "industry_missing_joint365": float(mask[mask.day.eq(365)].four_state_brier.mean())}
    json_once(out / "report_tables.json", tables)
    lines = []
    for title in ("source_models", "fresh_models", "fresh_worlds_selected", "source_support", "fresh_bootstrap365"):
        rows = tables[title]
        columns = list(rows[0])
        lines.extend([f"## {title}", "", "| " + " | ".join(columns) + " |", "| " + " | ".join(["---"]*len(columns)) + " |"])
        for row in rows:
            lines.append("| " + " | ".join(f"{row[c]:.6f}" if isinstance(row[c], float) else str(row[c]) for c in columns) + " |")
        lines.append("")
    path = out / "report_tables.md"
    data = ("\n".join(lines)+"\n").encode()
    if path.exists() and path.read_bytes() != data:
        raise ValueError("Existing report tables differ")
    if not path.exists():
        path.write_bytes(data)
    code = json.loads((out / "code.lock.json").read_text(encoding="utf-8"))
    if any(digest(ROOT / rel) != sha for rel, sha in code.items()):
        raise ValueError("Current locked implementation differs")
    snapshot = out / "source_snapshot.zip"
    if not snapshot.exists():
        with zipfile.ZipFile(snapshot, "x", compression=zipfile.ZIP_DEFLATED) as z:
            for rel in code:
                z.write(ROOT / rel, rel)
            for p in (ROOT / "analysis").glob("*practical*.py"):
                z.write(p, p.relative_to(ROOT).as_posix())
    suite = ElementTree.parse(out / "tests.xml").find(".//testsuite")
    tests = {k: int(suite.attrib[k]) for k in ["tests", "failures", "errors", "skipped"]}
    verification = {"tests": tests, "baseline_model_sha256_equal": digest(out / "models/v6.txt") == digest(ORIGINAL / "model.txt"),
                    "initial_fresh_design_unchanged": True, "fresh_receipts_match_frozen_selection": True,
                    "no_fresh_reselection": not summary["fresh_selection_performed"],
                    "protected_files_checked": summary["protected_files_checked"], "changed_protected_files": summary["changed_protected_files"],
                    "protocol_sha256": digest(out / "protocol.lock.json"), "selection_sha256": receipt_hash,
                    "report_sha256": digest(out / "report_tables.json"), "source_snapshot_sha256": digest(snapshot)}
    json_once(out / "verification.json", verification)
    print(json.dumps({"selected": chosen, "fresh_checks_pass": summary["all_fresh_research_checks_pass"],
                      "fresh_models": tables["fresh_models"], "verification": verification}, indent=2), flush=True)


if __name__ == "__main__":
    main()
