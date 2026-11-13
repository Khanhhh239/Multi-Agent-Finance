"""Dated production landmarks, censored weekly likelihood and common cash scoring.

Features are frozen at each origin. Only labels available by label_end are used;
an unobserved future week never becomes a negative training example.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .cash_adapter import expected_cash, probabilities
from .compact_t1 import workspace_context
from .data import as_of, effective_data, fingerprint, observed
from .landmark_features import FEATURES, prepare_features
from .payment_coverage import followup_days


def visible_data(data, cutoff):
    """Remove knowledge after cutoff from both consumers and evidence hashes."""
    limit = str(pd.Timestamp(cutoff).date())
    selected = dict(as_of(data, cutoff))
    selected.setdefault("payment_coverage", [])
    for kind, rows in selected.items():
        if isinstance(rows, list):
            selected[kind] = [
                r
                for r in rows
                if not isinstance(r, dict)
                or str(r.get("known_at", r.get("available_on", "0001-01-01")))[:10]
                <= limit
            ]
    selected["record_history"] = {
        kind: [r for r in rows if r.get("known_at", "0001-01-01") <= limit]
        for kind, rows in data.get("record_history", {}).items()
    }
    return selected


HORIZON = 13
CASH = tuple(f"cash_{week}" for week in range(1, 14))
COLUMNS = (
    *FEATURES,
    "invoice_id",
    "customer_id",
    "origin",
    "label_end",
    "amount_open",
    "claim_amount",
    "paid_days",
    "followup_days",
    *CASH,
)


def landmarks(data, origin, label_end):
    origin, label_end = (
        pd.Timestamp(origin).normalize(),
        pd.Timestamp(label_end).normalize(),
    )
    if label_end < origin:
        raise ValueError("Ngày nhãn T1 phải từ origin trở đi")
    visible = as_of(data, origin)
    if not any(
        pd.Timestamp(row["issue_date"]) <= origin
        and pd.Timestamp(row["known_at"]) <= origin
        for row in visible.get("invoices", [])
    ):
        return pd.DataFrame(columns=COLUMNS)
    try:
        history = workspace_context(data, origin)
    except ValueError:
        if not as_of(data, origin).get("invoices"):
            return pd.DataFrame(columns=COLUMNS)
        raise
    opened = history[
        (history.remaining_amount > 0.01) & history.written_off_at.isna()
    ].copy()
    if opened.empty:
        return pd.DataFrame(columns=COLUMNS)
    outcome = observed(data, label_end).set_index("invoice_id")
    available = effective_data(data, label_end)
    payments = {}
    for row in available.get("payments", []):
        paid, known = pd.Timestamp(row["payment_date"]), pd.Timestamp(row["known_at"])
        if max(paid, known) <= label_end:
            payments.setdefault(row["invoice_id"], []).append(
                (paid, known, int(row["amount"]))
            )
    pieces, valid = [], []
    shared_followup = None
    if not any(r.get("invoice_ids") is not None or r.get("customer_ids") is not None
               for r in data.get("payment_coverage", [])):
        shared_followup = followup_days(data, origin, label_end, None, None)
    # Even a credit followed by a reversal invalidates a fixed-principal label;
    # equality of the two endpoint balances alone cannot prove an unchanged debt.
    revisions = {}
    for change in data.get("record_history", {}).get("invoices", []):
        if origin < pd.Timestamp(change["known_at"]) <= min(label_end, origin + pd.Timedelta(days=91)):
            revisions.setdefault(change["invoice_id"], []).append(change)
    for position, row in enumerate(opened.itertuples()):
        iid = row.invoice_id
        if iid not in outcome.index:
            continue  # Cancelled/replaced debt is not an unpaid observation.
        end = outcome.loc[iid]
        if (
            abs(float(end.amount) - float(row.amount)) > 0.01
            or end.customer_id != row.customer_id
        ):
            continue
        if any(c.get("_deleted") or ("amount" in c and float(c["amount"]) != float(row.amount))
               or ("customer_id" in c and c["customer_id"] != row.customer_id)
               for c in revisions.get(iid, [])):
            continue
        if pd.notna(end.written_off_at) and end.written_off_at <= min(
            label_end, origin + pd.Timedelta(days=91)
        ):
            continue
        followup = (shared_followup if shared_followup is not None else
                    followup_days(data, origin, label_end, iid, row.customer_id))
        entries = sorted(payments.get(iid, []), key=lambda p: (p[0], p[1]))
        if any(paid <= origin < known for paid, known, _ in entries):
            continue  # Late-linked old cash must not become a future receipt.
        if abs(sum(amount for paid, _, amount in entries if paid <= origin) - float(row.received)) > 0.01:
            continue  # Revision/deletion of old cash invalidates opening principal.
        cumulative = 0
        settlement = np.inf
        cash = np.zeros(13)
        for paid, _, amount in entries:
            cumulative += amount
            delay = (paid - origin).days
            if cumulative >= int(row.amount) and not np.isfinite(settlement):
                settlement = float(delay)
            if 1 <= delay <= followup:
                cash[(delay - 1) // 7] += amount / float(row.remaining_amount)
        if settlement <= 0 or cash.sum() > 1 + 1e-8:
            continue
        # Outcomes after the observation/horizon boundary stay censored.
        settlement = settlement if settlement <= followup else np.inf
        valid.append(position)
        pieces.append((settlement, cash, followup))
    if not valid:
        return pd.DataFrame(columns=COLUMNS)
    opened = opened.iloc[valid].reset_index(drop=True)
    values = prepare_features(opened, history, origin)
    frame = pd.DataFrame(values, columns=FEATURES)
    frame["invoice_id"] = opened.invoice_id.to_numpy()
    frame["customer_id"] = opened.customer_id.to_numpy()
    frame["origin"], frame["label_end"] = origin, label_end
    frame["amount_open"] = opened.remaining_amount.to_numpy(float)
    frame["claim_amount"] = opened.amount.to_numpy(float)
    frame["paid_days"] = [p[0] for p in pieces]
    frame["followup_days"] = [p[2] for p in pieces]
    frame[list(CASH)] = np.asarray([p[1] for p in pieces])
    return frame


def rolling_landmarks(data, label_end, *, lookback_days=730, stride_days=28):
    end = pd.Timestamp(label_end).normalize()
    # Include a seven-day-old origin exactly, independent of calendar phase.
    last = end - pd.Timedelta(days=7)
    visible = as_of(data, end)
    starts = [
        pd.Timestamp(r["issue_date"])
        for r in visible.get("invoices", [])
        if pd.Timestamp(r["known_at"]) <= end
    ]
    if not starts:
        return pd.DataFrame(columns=COLUMNS)
    first = max(min(starts), end - pd.Timedelta(days=lookback_days))
    clocks = (
        sorted(pd.date_range(last, first, freq=f"-{stride_days}D"))
        if first <= last
        else []
    )
    parts = [landmarks(data, t, end) for t in clocks]
    parts = [p for p in parts if not p.empty]
    return (
        pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    )


def risk_rows(frame, *, cap=12000, half_life_days=180.0, seed=261112):
    if frame.empty:
        raise ValueError("Không có snapshot T1 đủ tuần quan sát")
    origin = pd.to_datetime(frame.origin)
    reference = pd.to_datetime(frame.label_end).max()
    counts = frame.groupby("origin").invoice_id.transform("size").to_numpy(float)
    weights = (
        np.exp2(-(reference - origin).dt.days.to_numpy(float) / half_life_days) / counts
    )
    paid = frame.paid_days.to_numpy(float)
    followup = frame.followup_days.to_numpy(float)
    values = frame[list(FEATURES)].to_numpy(float)
    xs, ys, ws, owners = [], [], [], []
    for week in range(1, 14):
        event = (paid > 7 * (week - 1)) & (paid <= 7 * week)
        # Use complete weekly intervals, including for early observed events.
        # Including only events from a partially observed week would bias its
        # Bernoulli hazard upward; defer that interval until its end is known.
        at_risk = (paid > 7 * (week - 1)) & (followup >= 7 * week)
        indices = np.flatnonzero(at_risk)
        xs.append(np.column_stack((values[indices], np.full(len(indices), week))))
        ys.append(event[indices].astype(int))
        ws.append(weights[indices])
        owners.append(indices)
    x, y, w = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws)
    owner = np.concatenate(owners)
    if not len(y):
        raise ValueError("Không có tuần risk đã quan sát")
    take = np.sort(
        np.random.default_rng(seed).choice(len(y), min(cap, len(y)), replace=False)
    )
    x, y, w = x[take], y[take], w[take]
    w *= len(w) / w.sum()
    digest = hashlib.sha256(x.tobytes() + y.tobytes() + w.tobytes()).hexdigest()
    represented = frame.iloc[np.unique(owner[take])]
    return (x, y, w), {
        "snapshots": len(frame),
        "unique_invoices": int(frame.invoice_id.nunique()),
        "risk_rows_available": len(owner),
        "risk_rows_used": len(y),
        "event_rows": int(y.sum()),
        "unique_invoices_represented": int(represented.invoice_id.nunique()),
        "latest_origin": str(origin.max().date()),
        "label_end": str(reference.date()),
        "censored_snapshots": int((followup < 91).sum()),
        "sample_sha256": digest,
    }


def cash_fractions(distribution, frame, partial):
    return expected_cash(distribution, frame, partial)[:, :13]


def score(distribution, frame, *, partial=None, saved_cash=None):
    if frame.empty or (frame.followup_days.to_numpy(float) < 91).any():
        raise ValueError("Chấm T1 cần đủ 91 ngày theo dõi")
    cash = (
        cash_fractions(distribution, frame, partial)
        if saved_cash is None
        else np.asarray(saved_cash, float)
    )
    if (
        cash.shape != (len(frame), 13)
        or not np.isfinite(cash).all()
        or (cash < 0).any()
        or (cash.sum(1) > 1 + 1e-8).any()
    ):
        raise ValueError("Lịch dự thu đã lưu không hợp lệ")
    p = probabilities(distribution, len(frame))
    if p.shape[1] != 14:
        raise ValueError("Chấm T1 cần phân phối 13 tuần")
    amounts = frame.amount_open.to_numpy(float)
    cdf = np.cumsum(p[:, :13], axis=1)
    truth = frame.paid_days.to_numpy(float)[:, None] <= 7 * np.arange(1, 14)
    records = []
    for origin in sorted(frame.origin.unique()):
        take = (frame.origin == origin).to_numpy()
        a = amounts[take]
        total = a.sum()
        error = (
            (cash[take] - frame.loc[take, list(CASH)].to_numpy(float)) * a[:, None]
        ).sum(0) / total
        records.append(
            {
                "origin": str(pd.Timestamp(origin).date()),
                "score": float(0.5 * (abs(error).sum() + abs(np.cumsum(error)).mean())),
                "integrated_brier13": float(
                    np.average(((cdf[take] - truth[take]) ** 2).mean(1), weights=a)
                ),
                "cash_weekly_mae_vnd": float(abs(error).mean() * total),
                "cash_cumulative_mae_vnd": float(abs(np.cumsum(error)).mean() * total),
            }
        )
    metrics = {
        k: float(np.mean([r[k] for r in records])) for k in records[0] if k != "origin"
    }
    return dict(
        metrics,
        windows=records,
        snapshots=len(frame),
        unique_invoices=int(frame.invoice_id.nunique()),
    )


def predict(model, frame):
    return model.distribution_from_features(frame[list(FEATURES)].to_numpy(float))


def frame_receipt(frame, data, cutoff):
    return {
        "rows": len(frame),
        "dataset_sha256": fingerprint(visible_data(data, cutoff)),
        "frame_sha256": hashlib.sha256(
            frame.to_json(orient="split", date_format="iso").encode()
        ).hexdigest(),
    }


def snapshot_for_audit(
    data, cutoff, baseline, challenger, baseline_version, challenger_version, created_at
):
    for bundle in (baseline, challenger):
        if (pd.Timestamp(bundle.get("asof", bundle["partial"].fitted_through)) > pd.Timestamp(cutoff)
                or pd.Timestamp(bundle["partial"].fitted_through) > pd.Timestamp(cutoff)):
            raise ValueError("Bundle audit được học sau origin")
    frame = landmarks(data, cutoff, cutoff)
    if frame.empty:
        return None
    base, proposed = predict(baseline["model"], frame), predict(challenger["model"], frame)
    return {
        "origin": str(pd.Timestamp(cutoff).date()),
        "created_at": created_at,
        "baseline_version": baseline_version,
        "challenger_version": challenger_version,
        "invoice_ids": frame.invoice_id.tolist(),
        "claim_amounts": frame.claim_amount.tolist(),
        "amounts": frame.amount_open.tolist(),
        "baseline_distribution": base.tolist(),
        "challenger_distribution": proposed.tolist(),
        "adapter_version": baseline["partial"].version,
        "baseline_partial_sha256": baseline["partial"].digest,
        "challenger_partial_sha256": challenger["partial"].digest,
        "baseline_cash": cash_fractions(base, frame, baseline["partial"]).tolist(),
        "challenger_cash": cash_fractions(proposed, frame, challenger["partial"]).tolist(),
        "snapshot_sha256": frame_receipt(frame, data, cutoff)["frame_sha256"],
    }


def score_audit_snapshot(snapshot, data, cutoff, *, minimum_rows=20):
    if pd.Timestamp(cutoff) < pd.Timestamp(snapshot["origin"]) + pd.Timedelta(days=91):
        return {"status": "waiting_for_91_days"}
    if snapshot["created_at"][:10] > snapshot["origin"]:
        return {"status": "retrospective_snapshot_not_for_promotion"}
    from .cash_adapter import VERSION
    if snapshot.get("adapter_version") != VERSION:
        return {"status": "incompatible_cash_adapter"}
    truth = landmarks(data, snapshot["origin"], cutoff).set_index(
        "invoice_id", drop=False
    )
    ids, positions = [], []
    for i, iid in enumerate(snapshot["invoice_ids"]):
        if (
            iid in truth.index
            and truth.loc[iid, "followup_days"] >= 91
            and abs(truth.loc[iid, "amount_open"] - snapshot["amounts"][i]) < 0.01
            and abs(truth.loc[iid, "claim_amount"] - snapshot["claim_amounts"][i])
            < 0.01
        ):
            ids.append(iid)
            positions.append(i)
    if len(ids) < minimum_rows:
        return {"status": "insufficient_eligible_outcomes", "rows": len(ids)}
    truth = truth.loc[ids].reset_index(drop=True)
    result = {
        "status": "scored",
        "rows": len(ids),
        "excluded_rows": len(snapshot["invoice_ids"]) - len(ids),
    }
    for name in ("baseline", "challenger"):
        result[name] = score(
            np.asarray(snapshot[f"{name}_distribution"])[positions],
            truth,
            saved_cash=np.asarray(snapshot[f"{name}_cash"])[positions],
        )
    result["truth_asof"] = str(pd.Timestamp(cutoff).date())
    result["truth_dataset_sha256"] = fingerprint(as_of(data, cutoff))
    return result
