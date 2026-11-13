"""One as-of accounting/feature contract for fitting, runtime and explanation."""
from pathlib import Path
import json
import os
import uuid

import numpy as np
import pandas as pd

from experiments.t1_compact.historical_workspace import partial_distribution
from agent1.adaptive.compact_t1 import workspace_context, sha256
from agent1.adaptive.landmark_features import FEATURES, prepare_features
from agent1.adaptive.ledger_bridge import workspace_data, ledger_context, CONTRACT
from experiments.t1_compact.landmark_data import CASH_COLUMNS, OVERRIDE_COLUMNS, cash_labels
from experiments.t1_compact.train import world_ledgers, sample_indices


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary,path)


def calendar_settlements(ledger, label_end):
    """Cash-full settlement uses cash date, conditional on known receipts.

    Posting order must not move an event back to an earlier partial receipt.
    Noncash credits never enter this cumulative cash-paid target.
    """
    payments=ledger.payments[ledger.payments.available<=pd.Timestamp(label_end)].copy()
    payments=payments.sort_values(["date","available"],kind="stable")
    payments["cash_cumulative"]=payments.groupby("invoice_id").amount.cumsum()
    gross=ledger.invoices.set_index("invoice_id").amount
    full=payments[payments.cash_cumulative>=payments.invoice_id.map(gross)-.01]
    return full.groupby("invoice_id").date.min()


def correct_labels(frame, ledger, label_end):
    frame=frame.copy()
    dates=calendar_settlements(ledger,label_end).reindex(frame.invoice_id)
    days=(pd.Series(dates.array,index=frame.index)-frame.origin).dt.days.to_numpy(float)
    if (np.isfinite(days)&(days<=0)).any():
        raise ValueError("Eligible open landmark already cash-settled at origin")
    frame["paid_days"]=np.where(np.isfinite(days),days,np.inf)
    return frame


def landmarks(ledger, data, origin, label_end, world, firm, role, ids=None, cap=100, build_cash=True):
    origin = pd.Timestamp(origin)
    if not ((ledger.invoices.issue_date <= origin) & (ledger.invoices.known_at <= origin)).any():
        return pd.DataFrame()
    # The World ledger supplies targets only; every estimator input and cash
    # override comes from exactly the accounting view used by forecast()/SHAP.
    history = ledger_context(ledger, origin)
    opened = history[(history.remaining_amount > .01) & history.written_off_at.isna()].copy()
    if ids is not None:
        opened = opened.set_index("invoice_id", drop=False).loc[list(ids)].reset_index(drop=True)
    raw = opened.reset_index(drop=True)
    days, valid = ledger.labels(raw, origin, label_end)
    # Keep the same conservative accounting/late-cash eligibility population,
    # while correcting the event time independently of receipt posting order.
    settled=calendar_settlements(ledger,label_end).reindex(raw.invoice_id)
    corrected=(pd.Series(settled.array)-origin).dt.days.to_numpy(float)
    days=np.where(np.isfinite(corrected),corrected,np.inf)
    if ids is not None and not valid.all():
        raise ValueError("Eligibility changed in source cohort")
    positions = np.flatnonzero(valid)
    if ids is None:
        positions = positions[sample_indices(opened.iloc[positions], cap, f"{world}:{firm}:{origin.date()}")]
    opened = opened.iloc[positions].reset_index(drop=True)
    if opened.empty:
        return pd.DataFrame()
    raw = raw.iloc[positions].reset_index(drop=True)
    np.testing.assert_allclose(opened.remaining_amount, raw.remaining_amount, atol=.01, rtol=0)
    features = prepare_features(opened, history, origin)
    result = pd.DataFrame(features, columns=FEATURES)
    result["invoice_id"] = opened.invoice_id.to_numpy()
    result["origin"], result["paid_days"] = origin, days[positions]
    result["amount_open"] = opened.remaining_amount.to_numpy(float)
    result["world"], result["firm"], result["role"] = world, firm, role
    result["kind"] = role
    cash, clipped = cash_labels(ledger, raw, origin, label_end) if build_cash else (np.zeros((len(opened), 13)), np.zeros(len(opened), bool))
    result[list(CASH_COLUMNS)] = cash
    base = np.zeros((len(opened), 14))
    base[:, -1] = 1.
    override, support = partial_distribution(data, opened, origin, base, return_support=True) if build_cash else (base, np.zeros(len(opened), bool))
    result[list(OVERRIDE_COLUMNS)] = override
    result["partial_override"], result["cash_label_clipped"] = support, clipped
    result["history_invoices"] = len(history)
    result["history_settlements"] = int(history.settled.notna().sum())
    result["customer_settlements_raw"] = np.expm1(features[:, 7])
    return result


def prepare_existing(source, output, role, worlds=None):
    inventory = json.loads((source / "inventory.json").read_text(encoding="utf-8"))
    paths = []
    for entry in inventory:
        if entry["role"] != role or (worlds is not None and entry["name"] not in worlds):
            continue
        path = output / "prepared" / f"{entry['name']}.parquet"
        receipt = path.with_suffix(".json")
        if path.exists():
            record = json.loads(receipt.read_text(encoding="utf-8"))
            if record["sha256"] != sha256(path):
                raise ValueError("Aligned cache changed")
            paths.append(path)
            continue
        original_path = source / "prepared" / f"{entry['name']}.parquet"
        original = pd.read_parquet(original_path)
        label_end = {"train": "2023-12-31", "validation": "2024-06-30", "test": "2025-12-31"}[role]
        pieces = []
        for firm, ledger in world_ledgers(source / entry["directory"]):
            data = workspace_data(ledger)
            firm_rows = original[original.firm == firm]
            for stamp in (firm_rows.origin.min(), firm_rows.origin.max()):
                fast, canonical = ledger_context(ledger, stamp), workspace_context(data, stamp)
                columns = ["amount", "known_at", "settled", "settled_known_at", "received", "remaining_amount", "receipt_count", "received_28d", "last_receipt", "written_off_at"]
                for column in ("known_at", "settled", "settled_known_at", "last_receipt", "written_off_at"):
                    fast[column] = fast[column].astype("datetime64[ns]")
                    canonical[column] = canonical[column].astype("datetime64[ns]")
                pd.testing.assert_frame_equal(fast.set_index("invoice_id")[columns].sort_index(), canonical.set_index("invoice_id")[columns].sort_index(), check_dtype=False, check_names=False)
            for origin, part in firm_rows.groupby("origin", sort=True):
                frame = landmarks(ledger, data, origin, label_end, entry["name"], firm, role, ids=part.invoice_id, build_cash=role != "train")
                pieces.append(frame)
            print(f"Aligned {entry['name']}/{firm}", flush=True)
        frame = pd.concat(pieces, ignore_index=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        write(receipt, dict(sha256=sha256(path), contract=CONTRACT, source_sha256=sha256(original_path),
                            world=entry["name"], rows=len(frame), role=role))
        paths.append(path)
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
