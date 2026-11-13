"""Independently recompute T6 bank truth, scores and temporal replay from saved artifacts."""
import argparse
import csv
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from threadpoolctl import threadpool_limits

from agent1.adaptive.compact_t1 import load_research_t1_bundle
from agent1.adaptive.methods import forecast
from agent1.adaptive.data import observed, fingerprint
from scripts.business.backtest_t6_baseline import load_demo, sha256, write_json, cash_equivalent


def verify(output):
    p = json.loads((output/"protocol.json").read_text(encoding="utf-8"))
    receipt = json.loads((output/"verification.json").read_text(encoding="utf-8"))
    for name, digest in receipt["result_hashes"].items():
        assert sha256(output/name) == digest, name
    snapshot = json.loads((output/"snapshot.json").read_text(encoding="utf-8"))
    assert all(sha256(Path(r["snapshot"])) == r["sha256"] for r in snapshot["files"])
    contexts = json.loads((output/"contexts.json").read_text(encoding="utf-8"))
    with (output/"weekly.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with (output/"metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        metrics = list(csv.DictReader(stream))
    with (output/"ar_metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        ar_metrics = list(csv.DictReader(stream))
    original, _ = load_demo(output/"inputs")
    datasets = {("original", "raw_dai_phat", cutoff): original for cutoff in p["cutoff_dates"]}
    grouped = {}
    maximum = 0.
    ar_paths = {}
    checked_models = {}
    expected_books = {}

    def close(left, right, label, atol=.01):
        nonlocal maximum
        difference = abs(float(left)-float(right))
        maximum = max(maximum, difference)
        assert difference <= atol, (label, left, right)

    for context in contexts:
        dataset, profile, cutoff, model, scope = (context[k] for k in ("dataset", "profile", "cutoff", "model", "scope"))
        key = dataset, profile, cutoff
        if key not in datasets:
            datasets[key] = json.loads(gzip.decompress((output/"fixtures"/f"{cutoff}_{profile}.json.gz").read_bytes()))
        data = datasets[key]
        assert fingerprint(data) == context["data_hash"]
        if cutoff not in checked_models:
            trained_path = output/"models"/cutoff
            trained = json.loads((trained_path/"receipt.json").read_text(encoding="utf-8"))
            assert trained["sha256"] == sha256(trained_path/"bundle.pkl")
            checked_models[cutoff] = trained["sha256"]
        assert checked_models[cutoff] == context["workspace_bundle_sha256"]
        if dataset == "stress":
            assert all(r["issue_date"] <= cutoff and r["known_at"] <= cutoff for r in data["invoices"])
            for kind in ("bank", "payments", "statements", "invoices", "actions"):
                assert [r for r in data[kind] if r["known_at"] <= cutoff] == [
                    r for r in original[kind] if r["known_at"] <= cutoff], (kind, "Historical inputs changed")
        truth_asof = p["truth_asof"] if dataset == "original" else str(date.fromisoformat(cutoff)+timedelta(weeks=13))
        plan_path = output/"plans"/f"{cutoff}_{dataset}_{profile}_{model}_{scope}.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert not plan["new_credit_included"] and not any(w["new_credit_in"] for w in plan["weeks"])
        assert context["future_removal_invariance"]
        if model == "global75_25":
            assert plan["t1_provenance"]["source"] == "research_global_retained"
            assert not plan["t1_provenance"]["local_adaptation"]
        group = [r for r in rows if all(r[k] == str(context[k]) for k in ("dataset", "profile", "cutoff", "model", "scope"))]
        assert len(group) == 13
        grouped[(dataset, profile, cutoff, model, scope)] = group
        bank = {r["bank_id"]: r for r in data["bank"] if r["known_at"] <= truth_asof and r["account"] in context["accounts"]}
        opened = {r["invoice_id"] for r in plan["cash_decomposition"]["invoices"]}
        historical = {k: [r for r in v if r.get("known_at", "0001-01-01") <= cutoff] if isinstance(v, list) else v
                      for k, v in data.items()}
        if cutoff not in expected_books:
            frame = observed(historical, cutoff)
            written_off = {r["invoice_id"] for r in historical["actions"] if r["kind"] == "write_off" and r["date"] <= cutoff}
            expected_books[cutoff] = set(frame.loc[(frame.remaining_amount > .01) & ~frame.invoice_id.isin(written_off), "invoice_id"])
        expected_ids = expected_books[cutoff]
        assert opened == expected_ids and len(opened) == plan["open_invoices"]
        cumulative_ar = 0.
        for w, r in zip(plan["weeks"], group):
            for field, stored in (("balance", "predicted_balance"), ("low", "p10"), ("high", "p90"),
                                  ("cash_in", "predicted_in"), ("cash_out", "predicted_out")):
                close(w[field], r[stored], "plan/CSV "+field)
            close(w["below_floor_probability"], r["below_floor_probability"], "plan/CSV probability", atol=1e-12)
            previous = date.fromisoformat(cutoff)+timedelta(weeks=w["week"]-1)
            true_balance = 0
            for account in context["accounts"]:
                periods = [s for s in data["statements"] if s["account"] == account and
                           s["start_date"] <= w["date"] <= s["end_date"] and s["known_at"] <= truth_asof]
                assert len(periods) == 1
                s = periods[0]
                true_balance += s["opening_balance"]+sum(
                    b["amount"]*(1 if b["direction"] == "in" else -1) for b in bank.values()
                    if b["account"] == account and s["start_date"] <= b["date"] <= w["date"])
            ar = sum(pay["amount"] for pay in data["payments"] if pay["invoice_id"] in opened and
                     pay["known_at"] <= truth_asof and pay.get("bank_id") in bank and
                     str(previous) < bank[pay["bank_id"]]["date"] <= w["date"])
            cumulative_ar += ar
            close(r["actual_balance"], true_balance, "bank actual")
            close(r["actual_ar_in"], ar, "AR actual")
            close(r["actual_cumulative_ar_in"], cumulative_ar, "cumulative AR")
            close(r["balance_error"], w["balance"]-true_balance, "bank error")
            assert (r["shortfall"] == "True") == (true_balance < p["cash_floor"])
            assert (r["alert"] == "True") == (w["balance"] < p["cash_floor"] or w["below_floor_probability"] >= .25)
            assert abs(float(r["error_bridge_residual"])) <= .01
        path_key = cutoff, model
        path = np.asarray([r["ar_in"] for r in plan["cash_decomposition"]["weeks"]])
        if path_key in ar_paths:
            np.testing.assert_allclose(path, ar_paths[path_key], rtol=0, atol=.01)
        else:
            ar_paths[path_key] = path

    for m in metrics:
        subset = [r for r in rows if all(r[k] == m[k] for k in ("dataset", "profile", "model", "scope")) and
                  (m["horizon"] == "w1-13" or (int(r["week"]) <= 4 if m["horizon"] == "w1-4" else int(r["week"]) >= 5))]
        y, pred, lo, hi, prob = (np.array([float(r[k]) for r in subset]) for k in
                                ("actual_balance", "predicted_balance", "p10", "p90", "below_floor_probability"))
        truth, alert = (np.array([r[k] == "True" for r in subset]) for k in ("shortfall", "alert"))
        close(m["mae_balance_vnd"], np.mean(abs(pred-y)), "MAE")
        close(m["coverage80"], np.mean((lo <= y) & (y <= hi)), "coverage", atol=1e-12)
        close(m["mean_width80_vnd"], np.mean(hi-lo), "width")
        close(m["interval_score80_vnd"], np.mean(hi-lo+10*np.maximum(lo-y, 0)+10*np.maximum(y-hi, 0)), "interval score")
        close(m["brier_weekly_shortfall"], np.mean((prob-truth)**2), "Brier", atol=1e-12)
        assert int(m["actual_shortfall_weeks"]) == int(truth.sum())
        assert int(m["false_alert_weeks"]) == int((alert & ~truth).sum())
        assert int(m["missed_shortfall_weeks"]) == int((~alert & truth).sum())
        for field, numerator, denominator in (("recall_weekly", (alert & truth).sum(), truth.sum()),
                                              ("precision_weekly", (alert & truth).sum(), alert.sum())):
            if denominator:
                close(m[field], numerator/denominator, field, atol=1e-12)
            else:
                assert m[field] == ""
    for m in ar_metrics:
        subset = [r for r in rows if r["scope"] == "ar_only" and
                  all(r[k] == m[k] for k in ("dataset", "profile", "model")) and
                  (m["horizon"] == "w1-13" or (int(r["week"]) <= 4 if m["horizon"] == "w1-4" else int(r["week"]) >= 5))]
        errors = [float(r["predicted_balance"])-float(r["opening_balance"])-float(r["actual_cumulative_ar_in"]) for r in subset]
        close(m["mae_balance_vnd"], np.mean(abs(np.array(errors))), "AR cumulative MAE")

    replayed = 0
    # Verify saved models and rebuild selected plans directly, without the runner's wrapper.
    for model in ("workspace", "global75_25"):
        cutoff = p["cutoff_dates"][-1]
        folder = output/"models"/cutoff
        trained = json.loads((folder/"receipt.json").read_text(encoding="utf-8"))
        assert sha256(folder/"bundle.pkl") == trained["sha256"]
        bundle = pickle.loads((folder/"bundle.pkl").read_bytes())
        assert bundle["asof"] == cutoff and bundle["operating"].get("credit") is None
        if model == "global75_25":
            bundle = load_research_t1_bundle(output/"global_release", cutoff, bundle)
        for dataset, profile in (("original", "raw_dai_phat"), ("stress", "schedule_gap")):
            given = datasets[(dataset, profile, cutoff)]
            # This study uses flat demo tables. Physically remove every future row.
            past = {k: [r for r in v if r.get("known_at", "0001-01-01") <= cutoff] if isinstance(v, list) else v
                    for k, v in given.items()}
            name = f"{cutoff}_{dataset}_{profile}_{model}_ar_operating_schedule.json"
            saved = json.loads((output/"plans"/name).read_text(encoding="utf-8"))
            options = dict(bundle=bundle, include_operating=True, cash_floor=p["cash_floor"],
                           simulation_paths=1000, simulation_seed=7, shap_limit=0)
            rebuilt = forecast(past, cutoff, saved["opening_balance"], **options)
            assert cash_equivalent(saved, rebuilt)
            replayed += 1
    result = dict(passed=True, verifier_sha256=sha256(Path(__file__)),
        raw_bank_truth_checks=len(rows), independent_bank_metric_groups=len(metrics), independent_ar_metric_groups=len(ar_metrics),
        rebuilt_from_saved_models=replayed, ar_invariant_across_scopes_and_stress=True,
        maximum_numeric_difference_vnd=maximum, snapshot_hashes_checked=len(snapshot["files"]),
        new_invoice_forecasting=False, protocol_sha256=sha256(output/"protocol.json"),
        synthetic_only=True, independent_firms=1)
    write_json(output/"independent_verification.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"outputs/t6/global_scope_no_new_credit_20261113")
    args = parser.parse_args()
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        verify(args.output.resolve())
