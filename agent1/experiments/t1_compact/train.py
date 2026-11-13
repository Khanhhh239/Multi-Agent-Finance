"""Time- and World-separated compact T1 fitting, selection, ablation and audit.

Run only after prepare_worlds.py. Validation chooses every feature/model;
test is evaluated once after freezing the artifact. No test World is fitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
import pandas as pd
import lightgbm as lgb
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import CompactT1, FEATURES, Ledger, SCHEMA, sha256, explain_compact

PROTOCOL = dict(
    version="compact-t1-world-training-v1", seed=261112,
    feature_schema=SCHEMA, max_state_features=10, max_shap_groups=6,
    fit_first="2020-01-06", fit_last="2023-09-25", fit_label_end="2023-12-31",
    validation_origins=["2024-01-01", "2024-01-29", "2024-02-26", "2024-03-25"],
    selection_label_end="2024-06-30", available_asof="2024-07-01",
    test_origins=["2024-07-01", "2024-09-30", "2024-12-30", "2025-03-31", "2025-06-30", "2025-09-29"],
    test_label_end="2025-12-31", stride_days=28, max_anchors_per_firm_origin=40,
    max_fit_anchors_per_firm=1100, max_eval_anchors_per_firm_origin=100,
    weighting="equal_world_then_firm; equal_origin_sampled_open_invoices; no class rebalancing",
    target="cash_full_settlement within 4/13 weeks of an observed open landmark; nonpaid outcomes remain in the unresolved tail",
    score="equal-World mean of mean(Paid Brier4, Paid Brier13)",
    feature_drop_relative_tolerance=.002,
    feature_selection="backward elimination on validation only, scalar features excluding mandatory term and age; one pass in declared order",
    shap_budget=dict(single_invoice_p95_seconds=1., queue20_p95_seconds=10., background_max=24, coalitions_max=64),
    limitations=["Regenerated retained configurations are reference scenarios, not pristine fresh tests.",
                 "Additional stress test seed is locked before fitting; simulator-family validation is not real-world acceptance.",
                 "Known ledger allocations, not private invoice truth, determine observed receipt histories.",
                 "Credit-note and late-known pre-origin cash revisions are excluded from fixed-claim label evaluation and counted.",
                 "This experiment does not change T6 partial-cash profiles or missing bank inflow/outflow scopes."])


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def world_ledgers(directory):
    inv = pd.read_parquet(directory/"invoices.parquet")
    pay = pd.read_parquet(directory/"payments.parquet")
    # Explicit allowlist: no is_bad_debt, liquidity, stress, future paid dates,
    # true customer state, private industry or customer ID as model features.
    for firm, invoices in inv.groupby("firm_id", sort=True):
        normal = invoices[["invoice_id", "firm_id", "customer_id", "issue_date", "due_date", "amount_gross", "writeoff_date"]].rename(columns={"amount_gross":"amount", "writeoff_date":"written_off_at"})
        normal["known_at"] = normal.issue_date
        p = pay[pay.firm_id == firm][["ledger_invoice_id", "pay_date_true", "ledger_post_date", "amount"]].rename(columns={"ledger_invoice_id":"invoice_id", "pay_date_true":"date", "ledger_post_date":"known_at"})
        credits = invoices[invoices.credit_note > 0][["invoice_id", "credit_note_date", "credit_note"]].rename(columns={"credit_note_date":"date", "credit_note":"amount"})
        credits["known_at"] = credits.date
        yield str(firm), Ledger(normal, p, credits)


def sample_indices(opened, count, seed):
    # Fixed hash order makes the sampling independent of dataframe row order.
    ranks = np.array([hashlib.sha256(f"{seed}:{iid}".encode()).digest()[:8] for iid in opened.invoice_id], dtype="S8")
    return np.argsort(ranks, kind="stable")[:count]


def prepare_frames(output, inventory):
    prepared = output/"prepared"
    prepared.mkdir(exist_ok=True)
    audits, paths = [], []
    for entry in inventory:
        path = prepared/f"{entry['name']}.parquet"
        hashfile = path.with_suffix(".json")
        if path.exists():
            saved = json.loads(hashfile.read_text())
            if saved["sha256"] != sha256(path) or saved["protocol_sha256"] != sha256(output/"protocol.json") or saved["replay_manifest_sha256"] != entry["replay_manifest_sha256"]:
                raise ValueError("Prepared data changed; use a new experiment directory")
            audits.append(saved)
            paths.append(path)
            continue
        directory = output/entry["directory"]
        receipt = json.loads((directory/"replay_manifest.json").read_text())
        for file, expected in receipt["files"].items():
            if sha256(directory/file) != expected:
                raise ValueError(f"World input hash mismatch: {directory/file}")
        if entry["role"] == "train":
            origins = pd.date_range(PROTOCOL["fit_first"], PROTOCOL["fit_last"], freq="28D")
            label_end = PROTOCOL["fit_label_end"]
        elif entry["role"] == "validation":
            origins, label_end = map(pd.Timestamp, PROTOCOL["validation_origins"]), PROTOCOL["selection_label_end"]
            origins = list(origins)
        else:
            origins = list(map(pd.Timestamp, PROTOCOL["test_origins"]))
            label_end = PROTOCOL["test_label_end"]
        pieces, counts = [], dict(open_anchors=0, excluded_accounting_or_late_cash=0)
        for firm, ledger in world_ledgers(directory):
            firm_parts = []
            for origin in origins:
                opened, x = ledger.snapshot_features(origin)
                if opened.empty:
                    continue
                days, valid = ledger.labels(opened, origin, label_end)
                counts["open_anchors"] += len(opened)
                counts["excluded_accounting_or_late_cash"] += int((~valid).sum())
                positions = np.flatnonzero(valid)
                valid_frame = opened.iloc[positions]
                limit = PROTOCOL["max_anchors_per_firm_origin"] if entry["role"] == "train" else PROTOCOL["max_eval_anchors_per_firm_origin"]
                chosen = positions[sample_indices(valid_frame, limit, f"{entry['name']}:{firm}:{origin.date()}")]
                part = pd.DataFrame(x[chosen], columns=FEATURES)
                part["invoice_id"] = opened.iloc[chosen].invoice_id.to_numpy()
                part["origin"] = origin
                part["paid_days"] = days[chosen]
                part["amount_open"] = opened.iloc[chosen].remaining_amount.to_numpy(float)
                firm_parts.append(part)
            if not firm_parts:
                continue
            part = pd.concat(firm_parts, ignore_index=True)
            if entry["role"] == "train" and len(part) > PROTOCOL["max_fit_anchors_per_firm"]:
                rng = np.random.default_rng(PROTOCOL["seed"])
                part = part.iloc[np.sort(rng.choice(len(part), PROTOCOL["max_fit_anchors_per_firm"], replace=False))].copy()
            part["firm"] = firm
            pieces.append(part)
        frame = pd.concat(pieces, ignore_index=True)
        frame["world"] = entry["name"]
        frame["role"] = entry["role"]
        frame["kind"] = entry["kind"]
        frame.to_parquet(path, index=False)
        audit = dict(world=entry["name"], role=entry["role"], kind=entry["kind"], firms=frame.firm.nunique(), anchors=len(frame), unique_invoices=frame.invoice_id.nunique(),
                     min_origin=str(frame.origin.min().date()), max_origin=str(frame.origin.max().date()), label_end=label_end,
                     sha256=sha256(path), protocol_sha256=sha256(output/"protocol.json"), replay_manifest_sha256=entry["replay_manifest_sha256"], **counts)
        write_json(hashfile, audit)
        audits.append(audit)
        paths.append(path)
        print(f"Prepared {entry['name']}: {len(frame)} anchors", flush=True)
    write_json(output/"data_audit.json", audits)
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def risk_rows(frame, active, feature_names=FEATURES):
    x = frame[list(feature_names)].to_numpy(float)
    days = frame.paid_days.to_numpy(float)
    rows, labels, weights = [], [], []
    # A surviving landmark contributes each weekly risk interval until cash
    # settlement. Writeoff/credit-only closure is not censored as if independent
    # of future payment: it has no full-cash event within the mature horizon.
    firm_count = frame.groupby("world").firm.transform("nunique").to_numpy(float)
    origins = frame.groupby(["world", "firm"]).origin.transform("nunique").to_numpy(float)
    anchors = frame.groupby(["world", "firm", "origin"]).invoice_id.transform("size").to_numpy(float)
    mass = 1/(firm_count*origins*anchors)
    for k in range(1, 14):
        take = days > (k-1)*7
        rows.append(np.column_stack((x[take][:, active], np.full(take.sum(), k))))
        labels.append((days[take] <= k*7).astype(int))
        weights.append(mass[take])
    w = np.concatenate(weights)
    w *= len(w)/w.sum()
    return np.concatenate(rows), np.concatenate(labels), w


def fit(frame, active, params):
    x, y, w = risk_rows(frame, active)
    dataset = lgb.Dataset(x, label=y, weight=w, feature_name=[FEATURES[i] for i in active]+["future_week"])
    booster = lgb.train(dict(objective="binary", verbosity=-1, num_threads=2, seed=PROTOCOL["seed"],
                             deterministic=True, force_col_wise=True, max_bin=63,
                             feature_fraction=1., bagging_fraction=1., **params), dataset, num_boost_round=120)
    return CompactT1(booster, active), dict(risk_rows=len(y), events=int(y.sum()))


def metrics(model, frame):
    p = model.distribution_from_features(frame[list(FEATURES)].to_numpy(float))
    results = []
    for (world, firm), indices in frame.groupby(["world", "firm"]).groups.items():
        loc = frame.index.get_indexer(indices)
        part = frame.loc[indices]
        row = dict(world=world, firm=firm, kind=str(part.kind.iloc[0]), anchors=len(part))
        for horizon in (4, 13):
            prob = p[loc, :horizon].sum(1)
            truth = (part.paid_days <= horizon*7).to_numpy(float)
            error = (prob-truth)**2
            row[f"brier{horizon}"] = float(error.mean())
            row[f"amount_brier{horizon}"] = float(np.average(error, weights=part.amount_open))
            row[f"bias{horizon}"] = float((prob-truth).mean())
            # Fixed equal-width reliability bins, diagnostics only.
            bins = np.minimum((prob*10).astype(int), 9)
            row[f"ece{horizon}"] = float(sum(abs((prob-truth)[bins == b].sum()) for b in range(10))/len(prob))
        results.append(row)
    firms = pd.DataFrame(results)
    worlds = firms.groupby(["world", "kind"], as_index=False).mean(numeric_only=True)
    score = float(((worlds.brier4+worlds.brier13)/2).mean())
    return dict(score=score, brier4=float(worlds.brier4.mean()), brier13=float(worlds.brier13.mean()),
                ece4=float(worlds.ece4.mean()), ece13=float(worlds.ece13.mean())), firms, worlds


def benchmark(model, test, output):
    # Repeated end-to-end explanations for one invoice and a queue of 20,
    # including shared input preparation. No fake timing based on tree logs.
    sample = test[test.world == sorted(test.world.unique())[0]]
    sample = sample[sample.origin == sample.origin.max()].head(400)
    x = sample[list(FEATURES)].to_numpy(float)
    from agent1.adaptive.compact_t1 import prepare_features
    # Use the actual observed test ledger, not reconstructed synthetic feature
    # rows, for prepare() and the cold path measured below.
    inventory = json.loads((output/"inventory.json").read_text())
    entry = next(e for e in inventory if e["name"] == sample.world.iloc[0])
    firm = str(sample.firm.iloc[0])
    ledger = next(ledger for fid, ledger in world_ledgers(output/entry["directory"]) if fid == firm)
    origin = sample.origin.max()
    history = ledger.snapshot(origin)
    opened = history[(history.remaining_amount > .01) & history.written_off_at.isna()].copy()
    opened.attrs["compact_context"] = history
    prepared = model.prepare(opened)
    probs = model.distribution_from_features(prepared)[:, :4].sum(1)
    records = [dict(invoice_id=str(r.invoice_id), customer_id=str(r.customer_id), payment_probability_4w=float(probs[i])) for i, r in enumerate(opened.itertuples())]
    timings, cold = {}, {}
    for count in (1, min(20, len(records))):
        durations = []
        for repeat in range(21):
            rows = [dict(r) for r in records[:count]]
            started = time.perf_counter()
            explain_compact(rows, opened, [(1., model)], origin, model_asof=PROTOCOL["available_asof"])
            durations.append(time.perf_counter()-started)
        cold[str(count)] = durations[0]
        timings[str(count)] = dict(p50=float(np.median(durations[1:])), p95=float(np.quantile(durations[1:], .95)), max=float(max(durations)), repetitions=len(durations))
    result = dict(hardware=platform.processor(), python=platform.python_version(), cold_first_call_seconds=cold,
                  warm_seconds=timings, observed_open_population=len(opened), active_features=len(model.active),
                  feature_preparation_included=True, model_loading_included=False,
                  one_invoice_budget_pass=timings["1"]["p95"] <= 1. and cold["1"] <= 1.)
    write_json(output/"latency.json", result)
    return result


def run(output):
    output = Path(output).resolve()
    from experiments.t1_compact.audit_manifests import audit

    audit(output)
    protocol_path = output/"protocol.json"
    if (output/"test_results.json").exists():
        raise ValueError("Test already evaluated; preserve this run and use a new directory for changes")
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != PROTOCOL:
        raise ValueError("Protocol changed; use a new run")
    write_json(protocol_path, PROTOCOL)
    inventory = json.loads((output/"inventory.json").read_text())
    if len(inventory) != 14:
        raise ValueError("World generation is incomplete")
    frame = prepare_frames(output, inventory)
    train = frame[frame.role == "train"].reset_index(drop=True)
    validation = frame[frame.role == "validation"].reset_index(drop=True)
    test = frame[frame.role == "test"].reset_index(drop=True)
    if set(train.world) & (set(validation.world) | set(test.world)):
        raise ValueError("World split overlap")
    if train.origin.max()+pd.Timedelta(days=91) > validation.origin.min():
        raise ValueError("Unpurged training follow-up")
    if validation.origin.max()+pd.Timedelta(days=91) >= pd.Timestamp(PROTOCOL["available_asof"]):
        raise ValueError("Selection labels unavailable at model ready date")
    candidates = [dict(name="conservative", params=dict(num_leaves=9, min_data_in_leaf=100, learning_rate=.05, lambda_l2=10.)),
                  dict(name="moderate", params=dict(num_leaves=15, min_data_in_leaf=80, learning_rate=.05, lambda_l2=5.))]
    trials = []
    models = []
    for candidate in candidates:
        start = time.monotonic()
        model, risk = fit(train, tuple(range(len(FEATURES))), candidate["params"])
        m, _, _ = metrics(model, validation)
        record = dict(stage="model_selection", **candidate, **m, **risk, seconds=time.monotonic()-start)
        trials.append(record)
        models.append(model)
        print(json.dumps(record), flush=True)
    best = min(range(len(trials)), key=lambda i: trials[i]["score"])
    model, params = models[best], candidates[best]["params"]
    current, _, _ = metrics(model, validation)
    active = list(model.active)
    # Receipt amount/recency, customer count/delay, firm context, amount scale.
    # Terms and age are mandatory coordinates of this payment-time model.
    for feature in (7, 4, 6, 9, 0, 8, 5, 3):
        subset = [i for i in active if i != feature]
        trial, risk = fit(train, subset, params)
        m, _, _ = metrics(trial, validation)
        accepted = m["score"] <= current["score"]*(1+PROTOCOL["feature_drop_relative_tolerance"])
        trials.append(dict(stage="feature_ablation", feature=FEATURES[feature], active=[FEATURES[i] for i in subset], accepted=bool(accepted), **m, **risk))
        print(json.dumps(trials[-1]), flush=True)
        if accepted:
            active, model, current = subset, trial, m
    write_json(output/"selection.json", trials)
    fingerprint = hashlib.sha256(json.dumps(json.loads((output/"data_audit.json").read_text()), sort_keys=True).encode()).hexdigest()
    meta = dict(available_asof=PROTOCOL["available_asof"], data_fingerprint=fingerprint,
                source_sha256=sha256(ROOT/"agent1/adaptive/compact_t1.py"),
                training_script_sha256=sha256(Path(__file__)), protocol_sha256=sha256(protocol_path),
                validation=current, params=params, activation="candidate_only", synthetic=True)
    model.save(output/"artifact", meta)
    # Frozen artifact is written BEFORE any test metric is computed.
    frozen_hash = sha256(output/"artifact/metadata.json")
    test_metrics, firms, worlds = metrics(model, test)
    firms.to_csv(output/"test_by_firm.csv", index=False)
    worlds.to_csv(output/"test_by_world.csv", index=False)
    baseline, _ = fit(train, [0, 1, 2, 5, 6, 7], params)
    baseline_metrics, _, base_worlds = metrics(baseline, test)
    base_worlds.to_csv(output/"reference_by_world.csv", index=False)
    # This reduced landmark baseline isolates selected-state feature value; it
    # is not mislabeled as the original issuance-based Workspace algorithm.
    result = dict(candidate=test_metrics, reduced_landmark_reference=baseline_metrics,
                  reference_features=[FEATURES[i] for i in (0,1,2,5,6,7)],
                  artifact_metadata_sha256=frozen_hash, features=[FEATURES[i] for i in active],
                  fit_anchors=len(train), validation_anchors=len(validation), test_anchors=len(test),
                  train_worlds=train.world.nunique(), validation_worlds=validation.world.nunique(), test_worlds=test.world.nunique(),
                  fit_firms=train.groupby(["world", "firm"]).ngroups,
                  limitations=PROTOCOL["limitations"])
    write_json(output/"test_results.json", result)
    latency = benchmark(model, test, output)
    print(json.dumps(dict(result=result, latency=latency)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.output)
