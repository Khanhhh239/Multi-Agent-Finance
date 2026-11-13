"""Retrospective, tenant-adaptive Workspace T1 versus frozen World candidates.

Each Workspace fit sees one firm's dated history through its origin only. Test
Worlds never enter the frozen global models or a cross-company refit. This is
an explicitly reused-test diagnostic, not a fresh generalization estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
import warnings
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from agent1.adaptive.compact_t1 import CompactT1, sha256
from agent1.adaptive.data import observed
from agent1.adaptive.explanations import explain_collections
from experiments.t1_compact.historical_workspace import CATALOG, Method, train
from experiments.t1_compact.landmark_data import CASH_COLUMNS, OVERRIDE_COLUMNS
from experiments.t1_compact.train import world_ledgers
from experiments.t1_compact.train_landmark import (
    context_for, score_prediction, summarize_prediction,
)

SOURCE = ROOT / "outputs/t1/compact_world_20261112"
LANDMARK = ROOT / "outputs/t1/landmark18_survival_cash_20261112"
PREVIOUS = ROOT / "outputs/t1/compact_ensemble_20261112_v3"
MODELS = {
    "world18": LANDMARK / "artifact",
    "world10": PREVIOUS / "artifact",
    "world_survival": LANDMARK / "trials/survival_0/model",
}
MODEL_NAMES = ("workspace", *MODELS)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def protocol():
    sources = [Path(__file__), *sorted((ROOT / "agent1/adaptive").glob("*.py")),
               ROOT / "agent1_service/ingest/invoices.py", ROOT / "agent1_service/ingest/money.py"]
    return {
        "version": "workspace-worlds-retrospective-v1",
        "diagnostic_only": True,
        "role": "test",
        "test_used_previously": True,
        "global_refitting_on_test_worlds": False,
        "local_adaptation": "one tenant only; train() unchanged at each origin; all fit/validation/audit labels known by origin",
        "workspace_candidates": [r[0] for r in CATALOG if r[0] != "blend"],
        "workspace_neural_max_iter": int(os.environ.get("AGENT1_NEURAL_MAX_ITER", "100")),
        "workspace_neural_batch_size": int(os.environ.get("AGENT1_NEURAL_BATCH_SIZE", "128")),
        "insufficient_history": "unchanged Workspace no-bundle customer-history baseline",
        "selection": "no new model, feature, weight, threshold or hyperparameter search on these outcomes",
        "target": "same 5486 eligible sampled open-invoice landmarks, full-cash Paid and bounded actual cash, 13 weeks",
        "cash_path": "same partial-payment override as T6, applied to every candidate before aggregation",
        "aggregation": "equal World, then firm, then origin; normalized by outstanding claim per origin",
        "shap": "20 separate invoice calls at each firm's last origin, fresh request cache, model/context ready; census<=512 otherwise weighted strata plus three sensitivity samples",
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in sources},
        "inventory_sha256": sha256(SOURCE / "inventory.json"),
        "global_models": {name: {"directory": str(path.relative_to(ROOT)),
                                  "metadata_sha256": sha256(path / "metadata.json")}
                          for name, path in MODELS.items()},
    }


def workspace_data(ledger):
    """Observed ledger adapter; credit notes are dated claim versions, never cash.

    Updated claims become known after issuance, so the unchanged Workspace
    training gate excludes them as issuance-time training targets.
    """
    invoices = []
    for row in ledger.invoices.itertuples():
        invoices.append(dict(invoice_id=str(row.invoice_id), customer_id=str(row.customer_id),
                             issue_date=str(row.issue_date.date()), due_date=str(row.due_date.date()),
                             known_at=str(row.known_at.date()), amount=int(round(row.amount)), currency="VND"))
    versions = [dict(row) for row in invoices]
    by_id = {row["invoice_id"]: row for row in invoices}
    totals = {}
    for row in ledger.credits.sort_values("available").itertuples():
        totals[row.invoice_id] = totals.get(row.invoice_id, 0) + row.amount
        original = by_id[row.invoice_id]
        versions.append(dict(original, amount=max(0, int(round(original["amount"] - totals[row.invoice_id]))),
                             known_at=str(row.available.date())))
    payments = [dict(payment_id=f"receipt_{i}", invoice_id=str(row.invoice_id),
                     payment_date=str(row.date.date()), known_at=str(row.known_at.date()),
                     amount=int(round(row.amount)))
                for i, row in enumerate(ledger.payments.itertuples())]
    actions = [dict(event_id=f"writeoff_{row.invoice_id}", invoice_id=str(row.invoice_id),
                    kind="write_off", date=str(row.written_off_at.date()),
                    known_at=str(row.written_off_at.date()))
               for row in ledger.invoices.itertuples() if pd.notna(row.written_off_at)]
    return dict(invoices=invoices, payments=payments, actions=actions, outflows=[],
                record_history={"invoices": versions})


def past_data(data, origin):
    limit = str(pd.Timestamp(origin).date())
    return {key: ({kind: [r for r in rows if r["known_at"] <= limit]
                   for kind, rows in value.items()} if key == "record_history"
                  else [r for r in value if r["known_at"] <= limit])
            for key, value in data.items()}


def serving(bundle, frame, origin):
    if bundle is None:
        return [(1., Method("customer").fit(frame, origin))]
    if pd.Timestamp(bundle["asof"]) > pd.Timestamp(origin):
        raise ValueError("Future Workspace bundle")
    return [(bundle["weight"], bundle["model"]), (1 - bundle["weight"], bundle["anchor"])]


def fit_local(data, origin):
    """Use precisely the runtime learner and its pre-existing fallback rule."""
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            bundle = train(data, origin)
        return bundle, sorted({str(w.message) for w in caught}), None
    except ValueError as exc:
        if str(exc).startswith("Chưa đủ lịch sử:"):
            return None, [], str(exc)
        raise


def distribution(components, targets, origin):
    ages = (pd.Timestamp(origin) - targets.issue_date).dt.days.to_numpy()
    return sum(w * model.distribution(targets, ages, horizon=13)
               for w, model in components if w)


def shap_latency(opened, components, origin, output, firm):
    """Spread targets by amount; no warm cache is shared between requests."""
    positions = np.unique(np.linspace(0, len(opened) - 1, min(20, len(opened))).astype(int))
    order = np.argsort(opened.remaining_amount.to_numpy(), kind="stable")
    probability = distribution(components, opened, origin)[:, :4].sum(1)
    samples = []
    for position in order[positions]:
        row = opened.iloc[position]
        target = [dict(invoice_id=str(row.invoice_id), customer_id=str(row.customer_id),
                       payment_probability_4w=float(probability[position]))]
        started = time.perf_counter()
        reference = explain_collections(target, opened, components, pd.Timestamp(origin), model_asof=str(origin.date()))
        elapsed = time.perf_counter() - started
        explanation = target[0]["payment_explanation"]
        if explanation["status"] != "available" or explanation["additivity_error"] > 1e-10:
            raise ValueError("Workspace SHAP faithfulness failure")
        samples.append(dict(invoice_id=str(row.invoice_id), seconds=elapsed,
                            additivity_error=explanation["additivity_error"]))
    result = dict(firm=firm, origin=str(origin.date()), population=len(opened),
                  reference=target[0]["payment_explanation"]["reference"],
                  samples=samples, p95_seconds=float(np.quantile([r["seconds"] for r in samples], .95)),
                  model_loading_included=False, ledger_context_construction_included=False,
                  feature_preparation_included=True)
    write_json(output / "shap" / f"{firm}.json", result)
    return result


def run_world(output, world):
    if read_json(output / "protocol.json") != protocol():
        raise ValueError("Protocol or source changed")
    entry = next(e for e in read_json(SOURCE / "inventory.json") if e["name"] == world)
    if entry["role"] != "test":
        raise ValueError("Only declared test Worlds belong to this diagnostic")
    world_dir = SOURCE / entry["directory"]
    manifest = world_dir / "replay_manifest.json"
    if sha256(manifest) != entry["replay_manifest_sha256"]:
        raise ValueError("World manifest changed")
    for name in ("invoices.parquet", "payments.parquet"):
        if sha256(world_dir / name) != read_json(manifest)["files"][name]:
            raise ValueError("World ledger changed")
    frame = pd.read_parquet(LANDMARK / "prepared" / f"{world}.parquet").reset_index(drop=True)
    receipt = read_json(LANDMARK / "prepared" / f"{world}.json")
    if sha256(LANDMARK / "prepared" / f"{world}.parquet") != receipt["sha256"]:
        raise ValueError("Prepared landmarks changed")
    predictions = {name: np.zeros((len(frame), 14)) for name in MODEL_NAMES}
    for name, path in MODELS.items():
        model = CompactT1.load(path)
        predictions[name] = model.distribution_from_features(frame[list(model.feature_names)].to_numpy(float))
    details = []
    target_dir = output / world
    target_dir.mkdir(exist_ok=True)
    for firm, ledger in world_ledgers(world_dir):
        data = workspace_data(ledger)
        parts = frame[frame.firm == firm]
        for origin, part in parts.groupby("origin", sort=True):
            cache = target_dir / "checkpoints" / firm / str(origin.date())
            if cache.with_suffix(".json").exists():
                receipt = read_json(cache.with_suffix(".json"))
                if sha256(cache.with_suffix(".npz")) != receipt["prediction_sha256"]:
                    raise ValueError("Workspace checkpoint changed")
                with np.load(cache.with_suffix(".npz"), allow_pickle=False) as saved:
                    predictions["workspace"][part.index] = saved["distribution"]
                details.append(receipt)
                continue
            started = time.perf_counter()
            local = past_data(data, origin)
            history = observed(local, origin)
            # Independently check the serving view against the World ledger.
            snapshot = ledger.snapshot(origin).set_index("invoice_id")
            hist = history.set_index("invoice_id")
            np.testing.assert_allclose(hist.loc[part.invoice_id, "remaining_amount"], part.amount_open, atol=.01, rtol=0)
            np.testing.assert_allclose(hist.loc[part.invoice_id, "received"], snapshot.loc[part.invoice_id, "received"], atol=.01, rtol=0)
            np.testing.assert_array_equal(observed(data, origin).set_index("invoice_id").sort_index().remaining_amount,
                                          history.set_index("invoice_id").sort_index().remaining_amount)
            print(f"Fitting {world}/{firm}/{origin.date()}, history={len(history)}", flush=True)
            bundle, messages, fallback = fit_local(local, origin)
            components = serving(bundle, history, origin)
            targets = hist.loc[part.invoice_id].reset_index()
            p = distribution(components, targets, origin)
            np.testing.assert_allclose(p.sum(1), 1, atol=1e-12, rtol=0)
            predictions["workspace"][part.index] = p
            # Explain only open, non-written-off invoices, as forecast() does.
            opened = history[(history.remaining_amount > .01) & history.written_off_at.isna()].copy()
            if origin == parts.origin.max():
                shap_latency(opened, components, origin, target_dir, firm)
            record = dict(world=world, firm=firm, origin=str(origin.date()), anchors=len(part),
                          history_invoices=len(history), history_settlements=int(history.settled.notna().sum()),
                          history_customers=int(history.customer_id.nunique()),
                          local_training_available=bundle is not None,
                          selected_method=bundle["selected_method"] if bundle else "customer_fallback",
                          serving_weight=float(bundle["weight"]) if bundle else 0.,
                          audit=bundle["audit"] if bundle else None,
                          train_windows=bundle["windows"] if bundle else None,
                          fallback_reason=fallback, warnings=messages, seconds=time.perf_counter()-started,
                          future_removal_invariance=True)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(cache.with_suffix(".npz"), distribution=p)
            record["prediction_sha256"] = sha256(cache.with_suffix(".npz"))
            write_json(cache.with_suffix(".json"), record)
            details.append(record)
            print(f"Finished {world}/{firm}/{origin.date()}: {record['selected_method']} ({record['seconds']:.1f}s)", flush=True)
    np.savez_compressed(target_dir / "predictions.npz", **predictions)
    write_json(target_dir / "fits.json", details)
    write_json(target_dir / "receipt.json", dict(world=world, anchors=len(frame),
               prepared_sha256=sha256(LANDMARK / "prepared" / f"{world}.parquet"),
               prediction_sha256=sha256(target_dir / "predictions.npz")))


def summarize(output):
    if read_json(output / "protocol.json") != protocol():
        raise ValueError("Protocol or sources changed during execution")
    frames, fits, predictions, latency = [], [], {name: [] for name in MODEL_NAMES}, []
    for entry in read_json(SOURCE / "inventory.json"):
        if entry["role"] != "test":
            continue
        name = entry["name"]
        frame = pd.read_parquet(LANDMARK / "prepared" / f"{name}.parquet")
        receipt = read_json(output / name / "receipt.json")
        if receipt["prediction_sha256"] != sha256(output / name / "predictions.npz"):
            raise ValueError("Prediction hash mismatch")
        frames.append(frame)
        fits.extend(read_json(output / name / "fits.json"))
        with np.load(output / name / "predictions.npz", allow_pickle=False) as saved:
            for model in MODEL_NAMES:
                predictions[model].append(saved[model])
        latency.extend(read_json(p) for p in sorted((output / name / "shap").glob("*.json")))
    frame = pd.concat(frames, ignore_index=True)
    fit_frame = pd.DataFrame(fits)
    fit_frame.to_csv(output / "workspace_fits.csv", index=False)
    context = context_for(frame)
    results, by_world, by_firm, by_origin, slices = {}, [], [], [], []
    for name in MODEL_NAMES:
        p = np.concatenate(predictions[name])
        results[name] = score_prediction(summarize_prediction(p, context), context)
        for columns, records in ((["world"], by_world), (["world", "firm"], by_firm),
                                 (["origin"], by_origin)):
            for key, positions in frame.groupby(columns, sort=True).indices.items():
                keys = key if isinstance(key, tuple) else (key,)
                sub = frame.iloc[positions].reset_index(drop=True)
                ctx = context_for(sub)
                records.append(dict(model=name, **dict(zip(columns, map(str, keys))),
                                    anchors=len(sub), **score_prediction(summarize_prediction(p[positions], ctx), ctx)))
        # These are fixed descriptive slices, never used to tune model choice.
        masks = {
            "customer_no_paid_history_180d": frame.customer_settlements_180d == 0,
            "customer_some_paid_history_180d": frame.customer_settlements_180d > 0,
            "invoice_partially_paid": frame.received_fraction > 0,
            "invoice_no_receipt": frame.received_fraction == 0,
            "invoice_overdue_90d": frame.age_days - frame.term_days > 90,
            "invoice_other_age": frame.age_days - frame.term_days <= 90,
        }
        availability = frame.merge(fit_frame[["world", "firm", "origin", "local_training_available"]].assign(
            origin=lambda f: pd.to_datetime(f.origin)), on=["world", "firm", "origin"], how="left").local_training_available
        masks["workspace_train_available"] = availability.to_numpy(bool)
        masks["workspace_insufficient_history"] = ~availability.to_numpy(bool)
        for label, mask in masks.items():
            indices = np.flatnonzero(np.asarray(mask))
            if not len(indices):
                continue
            sub = frame.iloc[indices].reset_index(drop=True)
            ctx = context_for(sub)
            slices.append(dict(model=name, slice=label, anchors=len(sub),
                               **score_prediction(summarize_prediction(p[indices], ctx), ctx)))
    for filename, records in (("by_world.csv", by_world), ("by_firm.csv", by_firm),
                              ("by_origin.csv", by_origin), ("slices.csv", slices)):
        pd.DataFrame(records).drop(columns="windows").to_csv(output / filename, index=False)
    write_json(output / "results.json", dict(results=results, anchors=len(frame), worlds=frame.world.nunique(),
               firms=len(frame[["world", "firm"]].drop_duplicates()), origins=frame.origin.nunique(),
               local_fits=len(fits), trained_fits=int(fit_frame.local_training_available.sum()),
               fallback_fits=int((~fit_frame.local_training_available).sum()), latency=latency,
               diagnostic_only=True, global_models_refitted=False, local_models_use_only_origin_history=True))
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--world")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=2):
        if args.init:
            definition = protocol()
            if (output / "protocol.json").exists() and read_json(output / "protocol.json") != definition:
                raise ValueError("Use a new output directory for changed protocols")
            write_json(output / "protocol.json", definition)
        if args.world:
            run_world(output, args.world)
        if args.summarize:
            summarize(output)
