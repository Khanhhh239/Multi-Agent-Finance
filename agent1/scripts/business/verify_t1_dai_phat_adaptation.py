"""Independently check Dai Phat's saved adaptation scores against raw receipts."""
import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import pickle
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def close(actual, expected, money=False):
    np.testing.assert_allclose(actual, expected, atol=.01 if money else 1e-12, rtol=1e-12)


def run(output):
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    completed = json.loads((output / "verification.json").read_text(encoding="utf-8"))
    for name, expected in completed["result_hashes"].items():
        assert digest(output / name) == expected, name
    snapshot = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
    for entry in snapshot["files"]:
        assert digest(Path(entry["snapshot"])) == entry["sha256"], entry["snapshot"]
    invoices = {row["invoice_id"]: row for row in read_csv(output / "inputs/01_invoices.csv")}
    payments = read_csv(output / "inputs/03_payments.csv")
    payments = [row for row in payments if max(row["known_at"], row["payment_date"]) <= protocol["truth_asof"]]
    cumulative, settled = {}, {}
    for row in sorted(payments, key=lambda item: (item["payment_date"], item["payment_id"])):
        identifier = row["invoice_id"]
        cumulative[identifier] = cumulative.get(identifier, 0.) + float(row["amount"])
        if cumulative[identifier] >= float(invoices[identifier]["amount"]) - .01:
            settled.setdefault(identifier, row["payment_date"])
    weekly = read_csv(output / "weekly.csv")
    metrics = read_csv(output / "metrics.csv")
    origins = read_csv(output / "per_origin_metrics.csv")
    summaries = {name: [] for name in protocol["models"]}
    unique_anchors, checked_plans = 0, 0
    from agent1.adaptive.landmark_features import LandmarkHazard
    from agent1.adaptive.compact_t1 import load_research_t1_bundle
    global_model = load_research_t1_bundle(output / "global_release", protocol["cutoffs"][0])["model"]
    reference = next(member for member in global_model.members
                     if isinstance(member, LandmarkHazard) and member.name.startswith("neural"))
    with np.load(output / "adaptation_inputs/current_global_replay.npz", allow_pickle=False) as replay:
        feature_probe = replay["x"][:100]
    parameter_checks = []
    for cutoff in protocol["cutoffs"]:
        folder = output / "origins" / cutoff
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["protocol_sha256"] == digest(output / "protocol.json")
        for name, expected in receipt["files"].items():
            assert digest(folder / name) == expected, name
        models = pickle.loads((folder / "models.pkl").read_bytes())
        alpha = receipt.get("continuation_weight", 0.)
        if alpha > 0:
            fine_tuned = models["global_finetuned"]
            neural = fine_tuned if alpha == 1 else fine_tuned.members[-1]
            np.testing.assert_array_equal(reference.booster[:-1].transform(feature_probe),
                                          neural.booster[:-1].transform(feature_probe))
            original_nn = reference.booster.steps[-1][1]
            adapted_nn = neural.booster.steps[-1][1]
            change = sum(float(np.linalg.norm(after - before))
                         for before, after in zip(original_nn.coefs_, adapted_nn.coefs_))
            assert change > 0, "Active fine-tune has unchanged Neural weights"
            parameter_checks.append(dict(cutoff=cutoff, alpha=alpha, neural_weight_change_norm=change,
                                         frozen_preprocessor=True))
        frame = pd.read_parquet(folder / "evaluation_landmarks.parquet")
        unique_anchors += len(frame)
        days = np.array([(date.fromisoformat(settled[identifier]) - date.fromisoformat(cutoff)).days
                         if identifier in settled else np.inf for identifier in frame.invoice_id])
        close(days, frame.paid_days.to_numpy())
        truth_paid = days[:, None] <= np.arange(1, 14) * 7
        actual = np.zeros(13)
        ids = set(frame.invoice_id)
        for row in payments:
            lag = (date.fromisoformat(row["payment_date"]) - date.fromisoformat(cutoff)).days
            if row["invoice_id"] in ids and 1 <= lag <= 91:
                actual[(lag - 1) // 7] += float(row["amount"])
        amount = frame.amount_open.to_numpy(float)
        overrides = frame[[f"override_week_{week}" for week in range(1, 15)]].to_numpy(float)
        with np.load(folder / "probabilities.npz", allow_pickle=False) as saved:
            for model in protocol["models"]:
                probabilities = saved[model]
                assert probabilities.shape == (len(frame), 14)
                close(probabilities.sum(axis=1), 1.)
                assert (probabilities >= 0).all()
                cash = probabilities.copy()
                cash[frame.partial_override.to_numpy(bool)] = overrides[frame.partial_override.to_numpy(bool)]
                predicted = (cash[:, :13] * amount[:, None]).sum(axis=0)
                error = predicted - actual
                losses = (np.cumsum(probabilities[:, :13], axis=1) - truth_paid) ** 2
                brier = losses.mean(axis=0)
                integrated_brier = (amount / amount.sum()) @ losses.mean(axis=1)
                score = .5 * (abs(error).sum() + abs(error.cumsum()).mean()) / amount.sum()
                reported = next(row for row in origins if row["cutoff"] == cutoff and row["model"] == model)
                for value, column in ((score, "score"), (brier[3], "brier4"), (brier[12], "brier13"),
                                      (integrated_brier, "integrated_brier13")):
                    close(value, float(reported[column]))
                rows = sorted([row for row in weekly if row["cutoff"] == cutoff and row["model"] == model],
                              key=lambda row: int(row["week"]))
                assert len(rows) == 13
                close(predicted, [float(row["predicted_ar_in"]) for row in rows], money=True)
                close(actual, [float(row["actual_ar_in"]) for row in rows], money=True)
                lower = np.array([float(row["p10"]) - float(row["opening_balance"]) for row in rows])
                upper = np.array([float(row["p90"]) - float(row["opening_balance"]) for row in rows])
                summaries[model].append(dict(error=error, actual=actual, lower=lower, upper=upper,
                                             score=score, brier=brier, integrated_brier=integrated_brier))
                checked_plans += 1
    checked_groups = 0
    for model, cases in summaries.items():
        for horizon, indices in (("w1-13", slice(None)), ("w1-4", slice(0, 4)), ("w5-13", slice(4, 13))):
            errors = np.concatenate([case["error"][indices] for case in cases])
            cumulative_errors = np.concatenate([case["error"].cumsum()[indices] for case in cases])
            actual = np.concatenate([case["actual"].cumsum()[indices] for case in cases])
            lower = np.concatenate([case["lower"][indices] for case in cases])
            upper = np.concatenate([case["upper"][indices] for case in cases])
            expected = dict(mae_weekly_ar_vnd=abs(errors).mean(), mae_cumulative_ar_vnd=abs(cumulative_errors).mean(),
                            mae_balance_vnd=abs(cumulative_errors).mean(), bias_balance_vnd=cumulative_errors.mean(),
                            coverage80=((lower <= actual) & (actual <= upper)).mean(),
                            mean_width80_vnd=(upper-lower).mean(),
                            interval_score80_vnd=(upper-lower+10*np.maximum(lower-actual, 0)+10*np.maximum(actual-upper, 0)).mean(),
                            cash_score=np.mean([case["score"] for case in cases]),
                            brier4=np.mean([case["brier"][3] for case in cases]),
                            brier13=np.mean([case["brier"][12] for case in cases]),
                            integrated_brier13=np.mean([case["integrated_brier"] for case in cases]))
            row = next(row for row in metrics if row["model"] == model and row["horizon"] == horizon)
            for column, value in expected.items():
                close(value, float(row[column]), money=column.endswith("_vnd"))
            checked_groups += 1
    result = dict(passed=True, verifier_sha256=digest(Path(__file__)),
                  raw_cash_and_settlement_truth=True, model_origin_cases_checked=checked_plans,
                  independent_metric_groups=checked_groups, origin_invoice_snapshots=unique_anchors,
                  source_input_hashes_checked=len(snapshot["files"]),
                  fine_tune_parameter_checks=parameter_checks,
                  independent_companies=1, prospective_holdout=False)
    (output / "independent_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/t1/dai_phat_adaptation_20261113")
    run(parser.parse_args().output.resolve())
