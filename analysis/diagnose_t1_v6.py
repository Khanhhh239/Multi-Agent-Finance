"""Read-only v6 diagnosis; no fitting, calibration, or test-based selection.

Run: .venv/Scripts/python.exe -B -m analysis.diagnose_t1_v6
All new artifacts go to a separate diagnosis directory. Shock truth is used
only for retrospective slices, never as an estimator input.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
from html import escape
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from agent1.models import t1
from agent1.models.features import published_macro_as_of
from agent1.paths import ROOT, SYNTH
from agent1.synth.shocks import ShockEpisode, episode_path, exposure_vectors
from experiments.t1_competing_v6 import calibration
from experiments.t1_competing_v6.core import (
    OPEN, PAID, WRITEOFF, STATE_NAMES, expand_weekly, label_events,
    predict_hazards, state_at_day,
)
from experiments.t1_competing_v6.features import V6_FEATURES
from experiments.t1_competing_v6.run import build_frame, load_world

ARTIFACT = ROOT / "outputs/data/t1_competing_v6_20261101"
TEST = "v4_shortpay_4shock_20261028_test_000"
WO_FEATURES = V6_FEATURES[46:52]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def independent_labels(frame, invoices, label_end):
    """Reconstruct from raw closure dates, without calling v6 label_events."""
    raw = invoices.set_index("invoice_id").loc[frame.invoice_id].reset_index(drop=True)
    cutoff = frame.cutoff.reset_index(drop=True)
    terminal = raw.closed_date_true
    event_in_window = terminal.notna() & terminal.le(pd.Timestamp(label_end))
    cause_map = {"open": OPEN, "paid": PAID, "paid_after_credit_note": PAID,
                 "writeoff": WRITEOFF, "credit_note": 3}
    causes = raw.closure_type.map(cause_map).where(event_in_window, OPEN).to_numpy(int)
    obs = (pd.Timestamp(label_end) - cutoff).dt.days.to_numpy(int)
    days = (terminal - cutoff).dt.days.fillna(np.inf).to_numpy()
    return np.minimum(days, obs).astype(int), obs, causes, raw


def risk_counts(times, obs, causes):
    rows = []
    for k in range(1, 54):
        left, right = 7 * (k - 1), 7 * k
        risk = (times > left) & (obs >= right)
        event = risk & (times <= right)
        counts = np.bincount(np.where(event[risk], causes[risk], OPEN), minlength=4)
        rows.append({"week": k, "risk_n": int(risk.sum()),
                     **{f"n_{s}": int(counts[j]) for j, s in enumerate(STATE_NAMES)}})
    return pd.DataFrame(rows)


def audit_labels(frame, invoices, payments, label_end, scope):
    times, obs, causes, raw = independent_labels(frame, invoices, label_end)
    end = pd.Timestamp(label_end)
    paid = invoices.paid_date_true.notna()
    written = invoices.writeoff_date.notna()
    # Independently accumulate dated cash AND credit movements on each invoice.
    cash = payments[["invoice_id", "pay_date_true", "amount"]].rename(
        columns={"pay_date_true": "date", "amount": "cash"})
    credit = invoices.loc[invoices.credit_note_date.notna(),
                          ["invoice_id", "credit_note_date", "credit_note"]].rename(
        columns={"credit_note_date": "date", "credit_note": "credit"})
    movements = pd.concat([cash, credit], ignore_index=True).fillna({"cash": 0., "credit": 0.})
    movements = movements.groupby(["invoice_id", "date"], as_index=False)[["cash", "credit"]].sum()
    movements = movements.sort_values(["invoice_id", "date"])
    movements[["cum_cash", "cum_credit"]] = movements.groupby("invoice_id")[["cash", "credit"]].cumsum()
    face = movements.invoice_id.map(invoices.set_index("invoice_id").amount_gross)
    covered = movements.cum_cash.add(movements.cum_credit).ge(face - 1) & movements.cum_cash.gt(1)
    paid_dates = movements.loc[covered].groupby("invoice_id").date.min()
    reconstructed_paid = invoices.invoice_id.map(paid_dates)
    mismatch_paid = paid & reconstructed_paid.ne(invoices.paid_date_true)
    joined = payments.merge(invoices[["invoice_id", "writeoff_date"]], on="invoice_id", how="left")
    after_wo = joined.writeoff_date.notna() & joined.pay_date_true.gt(joined.writeoff_date)
    pay_at_wo = joined.loc[joined.writeoff_date.notna() & joined.pay_date_true.le(joined.writeoff_date)].groupby("invoice_id").amount.sum()
    wo_credit = invoices.credit_note.where(invoices.credit_note_date.le(invoices.writeoff_date), 0).fillna(0)
    wo_expected = (invoices.amount_gross - wo_credit - invoices.invoice_id.map(pay_at_wo).fillna(0)).clip(lower=0)
    expected_amount = wo_expected.where(written, 0)
    core_labeled = label_events(frame, label_end)
    counts = risk_counts(times, obs, causes)
    # Exercise the implementation's actual expansion on deterministic rows too.
    sample = frame.sample(min(512, len(frame)), random_state=20261105).reset_index(drop=True)
    _, expanded_y = expand_weekly(sample, V6_FEATURES)
    st, so, sc, _ = independent_labels(sample, invoices, label_end)
    expected_y = np.concatenate([
        np.where(st[(st > 7*(k-1)) & (so >= 7*k)] <= 7*k,
                 sc[(st > 7*(k-1)) & (so >= 7*k)], OPEN)
        for k in range(1, 54)
    ])
    cutoff = frame.cutoff.reset_index(drop=True)
    checks = {
        "label_time_mismatches": int(np.count_nonzero(frame.time_days.to_numpy() != times)),
        "label_cause_mismatches": int(np.count_nonzero(frame.cause.to_numpy() != causes)),
        "label_observation_mismatches": int(np.count_nonzero(frame.obs_days.to_numpy() != obs)),
        "core_label_mismatches": int(np.count_nonzero(core_labeled.cause.to_numpy() != causes)),
        "events_at_or_before_cutoff": int((raw.closed_date_true.notna() & raw.closed_date_true.le(cutoff)).sum()),
        "not_yet_issued": int(raw.issue_date.gt(cutoff).sum()),
        "duplicate_snapshot_keys": int(frame.duplicated(["world", "invoice_id", "cutoff"]).sum()),
        "label_end_beyond_source": int(invoices.observation_end.lt(end).any()),
        "raw_paid_writeoff_conflicts": int((paid & written).sum()),
        "raw_paid_date_cash_credit_mismatches": int(mismatch_paid.sum()),
        "raw_writeoff_amount_mismatches": int((invoices.writeoff_amount - expected_amount).abs().gt(1).sum()),
        "raw_payments_after_writeoff": int(after_wo.sum()),
        "actual_expand_order_or_label_mismatches": int(not np.array_equal(expanded_y, expected_y)),
    }
    return {"scope": scope, "n_snapshots": len(frame), "unique_invoices": int(frame.invoice_id.nunique()),
            "min_obs_days": int(obs.min()), "admin_censored": int((causes == 0).sum()),
            "open_at_365": int(((times > 365) | (causes == 0)).sum()),
            "partial_admin_week_snapshots": int((obs < 371).sum()),
            "weekly_rows": int(counts.risk_n.sum()),
            "weekly_labels": {s: int(counts[f"n_{s}"].sum()) for s in STATE_NAMES},
            "checks": checks}, counts


def feature_drift(source, target, comparison):
    rows = []
    for name in V6_FEATURES:
        a, b = source[name].to_numpy(float), target[name].to_numpy(float)
        av, bv = a[np.isfinite(a)], b[np.isfinite(b)]
        edges = np.unique(np.quantile(av, np.linspace(0, 1, 11))) if len(av) else np.array([])
        inner = edges[1:-1]
        def distribution(x):
            finite = np.isfinite(x)
            counts = np.bincount(np.searchsorted(inner, x[finite], side="right"), minlength=len(inner)+1)
            return np.r_[counts, (~finite).sum()] / len(x)
        pa, pb = distribution(a), distribution(b)
        pa, pb = np.maximum(pa, 1e-6), np.maximum(pb, 1e-6)
        pooled = np.sqrt((np.var(av) + np.var(bv)) / 2) if len(av) and len(bv) else np.nan
        rows.append({"comparison": comparison, "feature": name,
                     "source_n": len(a), "target_n": len(b),
                     "source_missing": float((~np.isfinite(a)).mean()), "target_missing": float((~np.isfinite(b)).mean()),
                     "source_mean": float(np.mean(av)) if len(av) else np.nan,
                     "target_mean": float(np.mean(bv)) if len(bv) else np.nan,
                     "source_p50": float(np.median(av)) if len(av) else np.nan,
                     "target_p50": float(np.median(bv)) if len(bv) else np.nan,
                     "source_p90": float(np.quantile(av, .9)) if len(av) else np.nan,
                     "target_p90": float(np.quantile(bv, .9)) if len(bv) else np.nan,
                     "smd": float((np.mean(bv)-np.mean(av))/pooled) if pooled > 0 else np.nan,
                     "ks": float(ks_2samp(av, bv).statistic) if len(av) and len(bv) else np.nan,
                     "psi": float(np.sum((pb-pa)*np.log(pb/pa))),
                     "target_outside_source_range": float(((bv < av.min()) | (bv > av.max())).mean()) if len(av) and len(bv) else np.nan})
    return pd.DataFrame(rows)


def pressure_context(frame, world):
    """Oracle severity annotations; deliberately kept out of model_view."""
    config = json.loads((SYNTH/world/"config.json").read_text(encoding="utf-8"))
    customers = pd.read_parquet(SYNTH/world/"customers.parquet").set_index("customer_id")
    firms = pd.read_parquet(SYNTH/world/"firms.parquet").set_index("firm_id")
    weeks = pd.date_range("2018-12-31", "2026-12-28", freq="W-MON")
    episodes = [ShockEpisode(**e) for e in config["shock_schedule"]]
    paths = [episode_path(e, weeks) for e in episodes]
    result = frame.copy()
    result["seller_industry"] = result.firm_id.map(firms.industry)
    result["buyer_industry"] = result.customer_id.map(customers.industry)
    for col in ("shock_origin_oracle", "shock_due_oracle", "shock_next13w_oracle"):
        result[col] = 0.
    for customer, indices in result.groupby("customer_id").groups.items():
        entity = customers.loc[customer].to_dict()
        pressures = exposure_vectors(episodes, paths, entity, len(weeks))
        total = sum(pressures.values())
        subset = result.loc[indices]
        origin_idx = np.searchsorted(weeks, subset.cutoff, side="right") - 1
        due_idx = np.searchsorted(weeks, subset.due_date, side="right") - 1
        result.loc[indices, "shock_origin_oracle"] = total[np.clip(origin_idx, 0, len(weeks)-1)]
        result.loc[indices, "shock_due_oracle"] = total[np.clip(due_idx, 0, len(weeks)-1)]
        result.loc[indices, "shock_next13w_oracle"] = np.array([total[j:j+13].mean() for j in origin_idx])
    return result


def add_bands(frame):
    f = frame.copy()
    f["overdue_band"] = pd.cut(f.days_past_due, [-np.inf, 0, 30, 60, 90, 180, np.inf],
                                labels=["not_overdue", "01_30", "31_60", "61_90", "91_180", "181_plus"]).astype(str)
    f["history_band"] = pd.cut(f.c_n_hist, [-np.inf, 0, 4, 19, np.inf],
                                labels=["0", "1_4", "5_19", "20_plus"]).astype(str)
    f["writeoff_history_band"] = np.where(f.c_writeoff_n_asof > 0, "has_prior_writeoff", "no_prior_writeoff")
    f["cutoff_month"] = f.cutoff.dt.strftime("%Y-%m")
    for name in ("shock_origin_oracle", "shock_due_oracle", "shock_next13w_oracle"):
        f[name+"_band"] = pd.cut(f[name], [-np.inf, 1e-12, .5, 1, 2, np.inf],
                                  labels=["none", "0_0.5", "0.5_1", "1_2", "2_plus"]).astype(str)
    return f


def score_rows(frame, h, scope, dimensions):
    rows = []
    groups = [("all", "all", np.arange(len(frame)))]
    for dimension in dimensions:
        groups += [(dimension, str(group), np.asarray(idx)) for group, idx in frame.groupby(dimension, observed=True).indices.items()]
    for day in (28, 91, 180, 270, 365):
        p = state_at_day(h, day)
        truth = np.where(frame.time_days.to_numpy() <= day, frame.cause.to_numpy(), OPEN)
        for dim, group, idx in groups:
            for cause, name in ((PAID, "paid"), (WRITEOFF, "writeoff")):
                actual = (truth[idx] == cause).astype(float)
                residual = p[idx, cause] - actual
                rows.append({"scope": scope, "day": day, "dimension": dim, "group": group,
                             "cause": name, "n": len(idx), "actual": float(actual.mean()),
                             "predicted": float(p[idx, cause].mean()), "gap": float(residual.mean()),
                             "brier": float(np.mean(residual**2)),
                             "expected_minus_actual_events": float(residual.sum()),
                             "contribution_to_global_gap": float(residual.sum()/len(frame)),
                             "amount_weighted_gap": float(np.average(residual, weights=frame.amount_open.to_numpy()[idx]))})
    return rows


def weekly_comparison(frame, h, scope):
    rows = []
    times, obs, causes = [frame[x].to_numpy() for x in ("time_days", "obs_days", "cause")]
    survival = np.ones(len(frame))
    for k in range(1, 54):
        left, right = 7*(k-1), 7*k
        risk = (times > left) & (obs >= right)
        for cause, name in ((PAID, "paid"), (WRITEOFF, "writeoff")):
            event = risk & (times <= right) & (causes == cause)
            n = int(risk.sum())
            predicted = float(h[risk, k-1, cause].mean()) if n else np.nan
            observed = float(event.sum()/n) if n else np.nan
            rows.append({"scope": scope, "week": k, "cause": name, "risk_n": n,
                         "events": int(event.sum()), "observed_hazard": observed,
                         "predicted_hazard_on_observed_risk": predicted,
                         "hazard_gap": predicted-observed,
                         "expected_events_on_observed_risk": predicted*n,
                         "model_risk_n": float(survival.sum()),
                         "observed_unconditional_event_mass": float(event.mean()),
                         "predicted_unconditional_event_mass": float(np.mean(survival*h[:, k-1, cause]))})
        survival *= h[:, k-1, OPEN]
    return rows


def permutation_diagnostic(booster, selected, frame, baseline_h, scope, repeats):
    baseline = pd.DataFrame(score_rows(frame, baseline_h, scope, []))
    rows = []
    for repeat in range(repeats):
        shuffled = frame.copy()
        rng = np.random.default_rng(20261105+repeat)
        for _, idx in shuffled.groupby("world").indices.items():
            order = rng.permutation(idx)
            shuffled.loc[idx, WO_FEATURES] = frame.loc[order, WO_FEATURES].to_numpy()
        h = calibration.transform(predict_hazards(booster, shuffled, V6_FEATURES, [0, 1, 2]), selected)
        permuted = pd.DataFrame(score_rows(frame, h, scope, []))
        for day in (28, 91, 365):
            for cause in ("paid", "writeoff"):
                a = baseline[(baseline.day == day) & (baseline.cause == cause)].iloc[0]
                b = permuted[(permuted.day == day) & (permuted.cause == cause)].iloc[0]
                rows.append({"scope": scope, "repeat": repeat, "day": day, "cause": cause,
                             "baseline_brier": a.brier, "permuted_brier": b.brier,
                             "brier_delta": b.brier-a.brier, "baseline_gap": a.gap,
                             "permuted_gap": b.gap})
    return rows


def plot_diagnostics(out, weekly, scores, drift):
    # Dependency-free standalone SVG: do not change the locked training environment.
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="760" viewBox="0 0 1100 760">',
           '<rect width="1100" height="760" fill="white"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#17253d;font-size:12px}.title{font-size:19px;font-weight:bold}</style>',
           '<text x="36" y="30" class="title">v6 / test_000: observed outcomes and predictions</text>',
           '<text x="36" y="53">Blue: observed; orange: v6. Conditional hazards use the same observed risk set.</text>']
    for j, cause in enumerate(("paid", "writeoff")):
        d = weekly[(weekly.scope == "test_000") & (weekly.cause == cause)]
        for row in range(2):
            x0, y0, w, height = 70+535*j, 115+335*row, 440, 230
            x = d.week.to_numpy() * (7 if row else 1)
            ys = [d.observed_hazard.to_numpy(), d.predicted_hazard_on_observed_risk.to_numpy()] if not row else [
                d.observed_unconditional_event_mass.cumsum().to_numpy(), d.predicted_unconditional_event_mass.cumsum().to_numpy()]
            top = max(float(np.nanmax(y)) for y in ys)*1.12
            top = max(top, .001)
            title = cause.capitalize() + (" cumulative incidence" if row else " weekly hazard")
            svg.append(f'<text x="{x0}" y="{y0-18}" class="title">{title}</text>')
            for fraction in np.linspace(0, 1, 5):
                yy = y0+height*(1-fraction)
                svg.append(f'<path d="M{x0} {yy}h{w}" stroke="#e2e8f0"/><text x="{x0-8}" y="{yy+4}" text-anchor="end">{top*fraction:.3f}</text>')
            for tick in ([1, 13, 26, 39, 53] if not row else [0, 91, 182, 273, 371]):
                xx = x0+w*tick/x.max()
                svg.append(f'<text x="{xx}" y="{y0+height+18}" text-anchor="middle">{tick}</text>')
            svg.append(f'<text x="{x0+w/2}" y="{y0+height+39}" text-anchor="middle">{"Days" if row else "Week"}</text>')
            for y, color in zip(ys, ("#2563eb", "#ea580c")):
                points = " ".join(f"{x0+w*xx/x.max():.2f},{y0+height*(1-yy/top):.2f}" for xx, yy in zip(x, y) if np.isfinite(yy))
                svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
    svg.append('</svg>')
    (out/"hazards_and_cif.svg").write_text("\n".join(svg), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"outputs/analysis/t1_v6_diagnosis_20261105")
    parser.add_argument("--permutation-repeats", type=int, default=3)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ARTIFACT/"protocol.lock.json").read_text(encoding="utf-8"))
    metadata = json.loads((ARTIFACT/"train.json").read_text(encoding="utf-8"))
    selected = json.loads((ARTIFACT/"calibration.json").read_text(encoding="utf-8"))
    # Register the complete original v6 artifact and the shared sources before reading.
    protected = {p: digest(p) for p in ARTIFACT.rglob("*") if p.is_file()}
    for directory in (ROOT/"experiments/t1_competing_v6", ROOT/"experiments/t1_competing_v5"):
        protected.update({p: digest(p) for p in directory.glob("*.py")})
    frames, selection_frames, audits, counts, macro_rows = [], [], [], [], []
    for detail in metadata["world_audit"]:
        world = detail["world"]
        print("Audit source", world, flush=True)
        cache = ARTIFACT/"cache"/f"train_{world}.parquet"
        assert digest(cache) == detail["cache_sha256"]
        cached = pd.read_parquet(cache)
        fit = cached[cached.partition.eq("fit")].reset_index(drop=True)
        selection_frames.append(cached[cached.partition.eq("calibration_select")])
        inv = pd.read_parquet(SYNTH/world/"invoices.parquet")
        pay = pd.read_parquet(SYNTH/world/"payments.parquet")
        audit, risk = audit_labels(fit, inv, pay, protocol["train_label_end"], world)
        audits.append(audit)
        counts.append(risk.assign(scope=world))
        frames.append(pressure_context(fit, world))
        macro = pd.read_parquet(SYNTH/world/"macro.parquet")
        for cutoff, part in fit.groupby("cutoff"):
            known = published_macro_as_of(macro, cutoff)
            macro_rows.append({"world": world, "scope": "train_fit", "cutoff": cutoff, "n": len(part),
                               "public_covid_asof": float(known.covid_stress.iloc[0]) if len(known) else np.nan})
        for p in (SYNTH/world).iterdir():
            if p.is_file():
                protected[p] = digest(p)
    train = add_bands(pd.concat(frames, ignore_index=True))
    source_selection = pd.concat(selection_frames, ignore_index=True)
    del frames, selection_frames, cached
    gc.collect()
    print("Rebuild exact test anchors", flush=True)
    for p in (SYNTH/TEST).iterdir():
        if p.is_file():
            protected[p] = digest(p)
    builder, receipts = load_world(TEST)
    cutoffs = pd.date_range(protocol["eval_first_cutoff"], protocol["eval_last_cutoff"], freq=f"{protocol['eval_stride_days']}D")
    test = build_frame(builder, TEST, cutoffs, protocol["eval_label_end"])
    test = test.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
    inv = pd.read_parquet(SYNTH/TEST/"invoices.parquet")
    pay = pd.read_parquet(SYNTH/TEST/"payments.parquet")
    audit, risk = audit_labels(test, inv, pay, protocol["eval_label_end"], "test_000")
    audits.append(audit)
    counts.append(risk.assign(scope="test_000"))
    test = add_bands(pressure_context(test, TEST))
    macro = pd.read_parquet(SYNTH/TEST/"macro.parquet")
    for cutoff, part in test.groupby("cutoff"):
        known = published_macro_as_of(macro, cutoff)
        macro_rows.append({"world": TEST, "scope": "test_000", "cutoff": cutoff, "n": len(part),
                           "public_covid_asof": float(known.covid_stress.iloc[0]) if len(known) else np.nan})
    del builder, receipts, inv, pay
    dump(out/"label_risk_audit.json", audits)
    risk_table = pd.concat(counts, ignore_index=True)
    risk_table.to_csv(out/"risk_set_counts.csv", index=False)
    expected_counts = {s: sum(a["weekly_labels"][s] for a in audits[:-1]) for s in STATE_NAMES}
    assert expected_counts == metadata["weekly_label_counts"], (expected_counts, metadata["weekly_label_counts"])
    assert all(not any(a["checks"].values()) for a in audits), audits
    drift = pd.concat([
        feature_drift(train, test, "all_fit_snapshots"),
        feature_drift(train.sort_values("cutoff").drop_duplicates(["world", "invoice_id"]), test, "first_sampled_anchor_per_invoice"),
        *[feature_drift(part, test, world) for world, part in train.groupby("world")]
    ], ignore_index=True)
    drift.to_csv(out/"feature_drift.csv", index=False)
    booster = lgb.Booster(model_file=str(ARTIFACT/"model.txt"))
    assert digest(ARTIFACT/"model.txt") == metadata["model_sha256"]
    importance = pd.DataFrame({"feature": booster.feature_name(), "gain": booster.feature_importance("gain"),
                               "split": booster.feature_importance("split")})
    importance["gain_share"] = importance.gain/importance.gain.sum()
    importance.sort_values("gain", ascending=False).to_csv(out/"feature_importance.csv", index=False)
    print("Predict test and disjoint source selection firms", flush=True)
    h_test = calibration.transform(predict_hazards(booster, test, V6_FEATURES, metadata["active_causes"]), selected)
    h_source = calibration.transform(predict_hazards(booster, source_selection, V6_FEATURES, metadata["active_causes"]), selected)
    exported = pd.read_parquet(ARTIFACT/"evaluation_predictions"/f"{TEST}.parquet")
    assert test.invoice_id.tolist() == exported.invoice_id.tolist()
    max_prediction_delta = max(float(np.max(np.abs(state_at_day(h_test, day)[:, cause] - exported[f"p_{name}_{day}d"].to_numpy())))
                               for day in (28, 91, 365) for cause, name in ((PAID, "paid"), (WRITEOFF, "writeoff")))
    assert max_prediction_delta < 1e-7
    dimensions = ["seller_industry", "buyer_industry", "overdue_band", "history_band", "writeoff_history_band", "cutoff_month", "firm_id", "customer_id",
                  "shock_origin_oracle_band", "shock_due_oracle_band", "shock_next13w_oracle_band"]
    scores = pd.DataFrame(score_rows(test, h_test, "test_000", dimensions) + score_rows(source_selection, h_source, "source_calibration_select", []))
    scores.to_csv(out/"subgroup_bias.csv", index=False)
    weekly = pd.DataFrame(weekly_comparison(test, h_test, "test_000") + weekly_comparison(source_selection, h_source, "source_calibration_select"))
    weekly.to_csv(out/"weekly_hazards.csv", index=False)
    bootstrap_rows = []
    rng = np.random.default_rng(20261105)
    firms = test.firm_id.unique()
    for day in (28, 91, 365):
        p = state_at_day(h_test, day)
        actual = np.where(test.time_days <= day, test.cause, OPEN)
        for cause, name in ((PAID, "paid"), (WRITEOFF, "writeoff")):
            f = pd.DataFrame({"firm": test.firm_id, "residual": p[:, cause]-(actual == cause)})
            grouped = f.groupby("firm").residual.agg(["sum", "size"]).reindex(firms)
            idx = rng.integers(0, len(firms), size=(1000, len(firms)))
            values = grouped["sum"].to_numpy()[idx].sum(axis=1)/grouped["size"].to_numpy()[idx].sum(axis=1)
            bootstrap_rows.append({"day": day, "cause": name, "gap": float(f.residual.mean()),
                                   "low": float(np.quantile(values, .025)), "high": float(np.quantile(values, .975)),
                                   "resampling_unit": "firm; one synthetic World"})
    pd.DataFrame(bootstrap_rows).to_csv(out/"gap_company_bootstrap.csv", index=False)
    # Label shift within age/history strata; no resampling by a future outcome.
    strata = ["overdue_band", "history_band"]
    mix_rows = []
    for scope, frame in (("train_fit", train), ("test_000", test)):
        for keys, part in frame.groupby(strata, observed=True):
            y = np.where(part.time_days <= 365, part.cause, OPEN)
            mix_rows.append({"scope": scope, "overdue_band": keys[0], "history_band": keys[1],
                             "n": len(part), "paid_365": float(np.mean(y == PAID)), "writeoff_365": float(np.mean(y == WRITEOFF))})
    mix = pd.DataFrame(mix_rows)
    mix.to_csv(out/"age_history_label_shift.csv", index=False)
    a = mix[mix.scope.eq("train_fit")].set_index(strata)
    b = mix[mix.scope.eq("test_000")].set_index(strata)
    common = a.index.intersection(b.index)
    reweight = {"test_support_fraction": float(b.loc[common, "n"].sum()/len(test)),
                **{name: float(np.average(a.loc[common, name], weights=b.loc[common, "n"])) for name in ("paid_365", "writeoff_365")}}
    pd.DataFrame(macro_rows).to_csv(out/"published_macro_asof.csv", index=False)
    print("Joint permutation of six write-off history features (diagnostic only)", flush=True)
    permutation = pd.DataFrame(
        permutation_diagnostic(booster, selected, source_selection, h_source, "source_calibration_select", args.permutation_repeats)
        + permutation_diagnostic(booster, selected, test, h_test, "test_000", args.permutation_repeats))
    permutation.to_csv(out/"writeoff_history_permutation.csv", index=False)
    test[["world", "invoice_id", "firm_id", "customer_id", "cutoff", "cause", "time_days", "days_past_due", "seller_industry", "buyer_industry",
          "shock_origin_oracle", "shock_due_oracle", "shock_next13w_oracle"]].to_parquet(out/"diagnostic_anchor_context.parquet", index=False)
    composition = pd.concat([train.assign(scope="train_fit"), test.assign(scope="test_000")], ignore_index=True)
    compositions = []
    for dim in dimensions:
        if dim in ("customer_id", "firm_id", "cutoff_month"):
            continue
        d = composition.groupby(["scope", dim], observed=True).size().rename("n").reset_index().rename(columns={dim: "group"})
        d["share"] = d.n/d.groupby("scope").n.transform("sum")
        d["dimension"] = dim
        compositions.append(d)
    pd.concat(compositions, ignore_index=True).to_csv(out/"composition.csv", index=False)
    plot_diagnostics(out, weekly, scores, drift)
    verification = {"original_files_checked": len(protected), "changed_original_files": [str(p.relative_to(ROOT)) for p, sha in protected.items() if digest(p) != sha],
                    "max_existing_prediction_delta": max_prediction_delta, "weekly_label_counts_match_train_metadata": True,
                    "all_label_risk_checks_pass": True, "source_file_sha256": digest(__file__),
                    "model_sha256": digest(ARTIFACT/"model.txt"), "fit_or_calibration_performed": False,
                    "scope": "Retrospective test_000 diagnosis; no model selection; oracle shock only in slices"}
    assert not verification["changed_original_files"]
    dump(out/"verification.json", verification)
    dump(out/"summary.json", {"train_snapshots": len(train), "source_selection_anchors": len(source_selection), "test_anchors": len(test),
                              "feature_count": len(V6_FEATURES), "wo_features": WO_FEATURES,
                              "writeoff_feature_gain_share": float(importance[importance.feature.isin(WO_FEATURES)].gain_share.sum()),
                              "age_history_reweighted_train_outcome_365": reweight,
                              "all_test_scores": scores[scores.dimension.eq("all")].to_dict("records"),
                              "verification": verification})
    print(json.dumps(verification, indent=2), flush=True)


if __name__ == "__main__":
    main()
