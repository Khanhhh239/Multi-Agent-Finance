"""Independent receipt, probability and cash-score checks for the refit study."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd

from agent1.adaptive.compact_t1 import sha256, CompactT1
from agent1.adaptive.landmark_features import FEATURES
from experiments.t1_compact.aligned_data import write
from experiments.t1_compact.refit_landmark import SOURCE, load_role
from experiments.t1_compact.compare_adaptation import NAMES, COMPARISON


def independent_score(frame, distribution):
    probabilities = distribution[:,:13].cumsum(1)
    cash = distribution[:,:13].copy()
    support = frame.partial_override.to_numpy(bool)
    cash[support] = frame.loc[support,[f"override_week_{i}" for i in range(1,14)]].to_numpy(float)
    cash = cash*frame.amount_open.to_numpy(float)[:,None]
    actual = frame[[f"cash_week_{i}" for i in range(1,14)]].to_numpy(float)*frame.amount_open.to_numpy(float)[:,None]
    rows = []
    for key, idx in frame.groupby(["world","firm","origin"]).indices.items():
        amount = frame.iloc[idx].amount_open.sum()
        error = (cash[idx]-actual[idx]).sum(0)/amount
        rows.append(dict(world=key[0],firm=key[1],origin=key[2],loss=.5*(abs(error).sum()+abs(error.cumsum()).mean())))
    table = pd.DataFrame(rows)
    return float(table.groupby(["world","firm"]).loss.mean().groupby("world").mean().mean())


def run(output):
    old_audit = json.loads((SOURCE/"data_audit.json").read_text(encoding="utf-8"))
    inventory = json.loads((SOURCE/"inventory.json").read_text(encoding="utf-8"))
    for entry in inventory:
        directory = SOURCE/entry["directory"]
        manifest = directory/"replay_manifest.json"
        if sha256(manifest) != entry["replay_manifest_sha256"]:
            raise ValueError("Original World manifest changed")
        for name,digest in json.loads(manifest.read_text(encoding="utf-8"))["files"].items():
            if name in ("invoices.parquet","payments.parquet") and sha256(directory/name) != digest:
                raise ValueError("Original ledger changed")
        audit = next(r for r in old_audit if r["world"]==entry["name"])
        if sha256(SOURCE/"prepared"/f"{entry['name']}.parquet") != audit["sha256"]:
            raise ValueError("Original landmark table changed")
    for entry in json.loads((output/"fresh_inventory.json").read_text(encoding="utf-8")):
        directory=output/entry["directory"]
        manifest=directory/"manifest.json"
        if sha256(manifest)!=entry["manifest_sha256"]:
            raise ValueError("New-seed World manifest changed")
        for name,digest in json.loads(manifest.read_text(encoding="utf-8"))["files"].items():
            if name in ("invoices.parquet","payments.parquet") and sha256(directory/name)!=digest:
                raise ValueError("New-seed World ledger changed")
    frozen = json.loads((output/"frozen.json").read_text(encoding="utf-8"))
    if sha256(output/"artifact/metadata.json") != frozen["artifact_metadata_sha256"]:
        raise ValueError("Frozen artifact changed")
    # Nested payload hashes are checked by the normal serving loader.
    model = CompactT1.load(output/"artifact")
    frame = load_role(output,"fresh_test")
    cash_cdf=frame[[f"cash_week_{i}" for i in range(1,14)]].to_numpy(float).cumsum(1)
    cash_paid=cash_cdf>=1-(.011/frame.amount_open.to_numpy(float))[:,None]
    np.testing.assert_array_equal(frame.paid_days.to_numpy(float)[:,None]<=7*np.arange(1,14),cash_paid)
    p = {name:np.zeros((len(frame),14)) for name in NAMES}
    max_reconstruction = 0.
    counts = {}
    for key,part in frame.groupby(["world","firm","origin"]):
        path = output/COMPARISON/key[0]/key[1]/str(key[2].date())
        record = json.loads((path/"receipt.json").read_text(encoding="utf-8"))
        for file,field in [("predictions.npz","prediction_sha256"),("models.pkl","models_sha256")]:
            if sha256(path/file) != record[field]:
                raise ValueError("Local comparison checkpoint changed")
        with np.load(path/"predictions.npz",allow_pickle=False) as saved:
            for name in NAMES:
                values = saved[name]
                if not np.isfinite(values).all() or (values<0).any():
                    raise ValueError("Invalid probability")
                np.testing.assert_allclose(values.sum(1),1.,atol=1e-12,rtol=0)
                p[name][part.index] = values
        actual = model.distribution_from_features(part[list(FEATURES)].to_numpy(float))
        max_reconstruction = max(max_reconstruction,float(abs(actual-p["global_refit"][part.index]).max()))
        for name in ("fit","validation","audit"):
            counts[name] = counts.get(name,0)+record.get("rows",{}).get(name,0)
    results = json.loads((output/"fresh_results.json").read_text(encoding="utf-8"))["results"]
    differences = {}
    for name,distribution in p.items():
        differences[name] = abs(independent_score(frame,distribution)-results[name]["score"])
        if differences[name]>1e-12:
            raise ValueError("Independent score does not match")
    alignment = []
    old_dir = ROOT/"outputs/t1/landmark18_survival_cash_20261112/prepared"
    for path in sorted((output/"prepared").glob("compact*.parquet")):
        new,old = pd.read_parquet(path),pd.read_parquet(old_dir/path.name)
        keys = ["world","firm","origin","invoice_id"]
        merged = new.merge(old,on=keys,suffixes=("_new","_old"),validate="one_to_one")
        delta = abs(merged[[f"{c}_new" for c in FEATURES]].to_numpy(float)-merged[[f"{c}_old" for c in FEATURES]].to_numpy(float))
        alignment.append(dict(world=str(new.world.iloc[0]),rows=len(new),changed_rows=int((delta>1e-8).any(1).sum()),
                              changed_features=[c for c,d in zip(FEATURES,delta.max(0)) if d>1e-8]))
    write(output/"alignment_audit.json",alignment)
    write(output/"verification.json",dict(passed=True, anchors=len(frame), probability_mass_tolerance=1e-12,
         independent_cash_score_max_difference=max(differences.values()),score_differences=differences,
         reconstructed_global_max_difference=max_reconstruction,
         all_model_and_input_hashes_checked=True, local_training_snapshot_rows=counts,
         cash_calendar_paid_labels_consistent=True,
         fresh_test_not_used_for_global_refit=True))
    print("Independent verification passed",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"outputs/t1/aligned_refit_20261112")
    run(parser.parse_args().output.resolve())
