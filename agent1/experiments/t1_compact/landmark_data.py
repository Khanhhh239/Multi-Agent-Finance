"""Rebuild the same eligible landmarks with eighteen observed state features."""

import json

import numpy as np
import pandas as pd
from experiments.t1_compact.historical_workspace import partial_distribution
from agent1.adaptive.compact_t1 import sha256
from agent1.adaptive.landmark_features import FEATURES, prepare_features
from experiments.t1_compact.train import PROTOCOL, world_ledgers, write_json

CASH_COLUMNS = tuple(f"cash_week_{week}" for week in range(1, 14))
OVERRIDE_COLUMNS = tuple(f"override_week_{week}" for week in range(1, 15))


def canonical_ledger(ledger):
    invoices = ledger.invoices[
        ["invoice_id", "customer_id", "issue_date", "due_date", "known_at", "amount"]
    ].copy()
    payments = (
        ledger.payments[["invoice_id", "date", "known_at", "amount"]]
        .rename(columns={"date": "payment_date"})
        .copy()
    )
    for frame, columns in (
        (invoices, ("issue_date", "due_date", "known_at")),
        (payments, ("payment_date", "known_at")),
    ):
        for column in columns:
            frame[column] = frame[column].dt.strftime("%Y-%m-%d")
    payments["payment_id"] = [
        f"receipt_{position}" for position in range(len(payments))
    ]
    return {
        "invoices": invoices.to_dict("records"),
        "payments": payments.to_dict("records"),
    }


def cash_labels(ledger, opened, origin, label_end):
    receipts = ledger.payments[
        (ledger.payments.available <= pd.Timestamp(label_end))
        & (ledger.payments.date > origin)
        & (ledger.payments.date <= origin + pd.Timedelta(days=91))
    ].copy()
    positions = pd.Series(np.arange(len(opened)), index=opened.invoice_id)
    receipts = receipts[receipts.invoice_id.isin(positions.index)]
    row = receipts.invoice_id.map(positions).to_numpy(int)
    week = ((receipts.date - origin).dt.days.to_numpy() - 1) // 7
    fractions = np.zeros((len(opened), 13))
    np.add.at(
        fractions,
        (row, week),
        receipts.amount.to_numpy(float) / opened.remaining_amount.to_numpy(float)[row],
    )
    cumulative = np.cumsum(fractions, axis=1)
    clipped = cumulative[:, -1] > 1.0 + 1e-8
    # The forecast target is recovery of the outstanding claim at origin.
    # Cash allocated above that claim belongs outside this bounded target.
    cumulative = np.minimum(cumulative, 1.0)
    return np.diff(
        np.column_stack((np.zeros(len(opened)), cumulative)), axis=1
    ), clipped


def prepare_role(source, output, role):
    audit = json.loads((source / "data_audit.json").read_text(encoding="utf-8"))
    inventory = json.loads((source / "inventory.json").read_text(encoding="utf-8"))
    prepared = output / "prepared"
    prepared.mkdir(exist_ok=True)
    frames, receipts = [], []
    for entry in audit:
        if entry["role"] != role:
            continue
        path = prepared / f"{entry['world']}.parquet"
        receipt_path = path.with_suffix(".json")
        if path.exists() and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt["sha256"] != sha256(path) or receipt[
                "protocol_sha256"
            ] != sha256(output / "protocol.json"):
                raise ValueError("Prepared landmark cache changed")
            frames.append(pd.read_parquet(path))
            receipts.append(receipt)
            continue
        old_path = source / "prepared" / f"{entry['world']}.parquet"
        if sha256(old_path) != entry["sha256"]:
            raise ValueError("Source landmark hash mismatch")
        original = pd.read_parquet(old_path)
        result = original.drop(
            columns=[
                column
                for column in original
                if column
                not in {
                    "invoice_id",
                    "origin",
                    "paid_days",
                    "amount_open",
                    "firm",
                    "world",
                    "role",
                    "kind",
                }
            ]
        ).copy()
        for column in FEATURES:
            result[column] = np.nan
        if role != "train":
            for column in (*CASH_COLUMNS, *OVERRIDE_COLUMNS):
                result[column] = np.nan
            result["partial_override"] = False
            result["cash_label_clipped"] = False
        world = next(item for item in inventory if item["name"] == entry["world"])
        manifest = source / world["directory"] / "replay_manifest.json"
        if sha256(manifest) != world["replay_manifest_sha256"]:
            raise ValueError("Source World manifest changed")
        files = json.loads(manifest.read_text(encoding="utf-8"))["files"]
        for name in ("invoices.parquet", "payments.parquet"):
            if sha256(manifest.parent / name) != files[name]:
                raise ValueError("Source World ledger changed")
        for firm, ledger in world_ledgers(manifest.parent):
            parts = original[original.firm == firm]
            if parts.empty:
                continue
            data = canonical_ledger(ledger) if role != "train" else None
            for origin, part in parts.groupby("origin", sort=True):
                history = ledger.snapshot(origin)
                opened = (
                    history.set_index("invoice_id", drop=False)
                    .loc[part.invoice_id]
                    .reset_index(drop=True)
                )
                if (
                    opened.remaining_amount <= 0.01
                ).any() or opened.written_off_at.notna().any():
                    raise ValueError("Source contains a closed landmark")
                np.testing.assert_allclose(
                    opened.remaining_amount, part.amount_open, atol=1e-8, rtol=0
                )
                result.loc[part.index, list(FEATURES)] = prepare_features(
                    opened, history, origin
                )
                if role == "train":
                    continue
                label_end = (
                    PROTOCOL["selection_label_end"]
                    if role == "validation"
                    else PROTOCOL["test_label_end"]
                )
                days, valid = ledger.labels(opened, origin, label_end)
                if not valid.all():
                    raise ValueError("Source label eligibility changed")
                np.testing.assert_array_equal(days, part.paid_days.to_numpy(float))
                cash, clipped = cash_labels(ledger, opened, origin, label_end)
                base = np.zeros((len(opened), 14))
                base[:, -1] = 1.0
                override, support = partial_distribution(
                    data, opened, origin, base, return_support=True
                )
                result.loc[part.index, list(CASH_COLUMNS)] = cash
                result.loc[part.index, list(OVERRIDE_COLUMNS)] = override
                result.loc[part.index, "partial_override"] = support
                result.loc[part.index, "cash_label_clipped"] = clipped
        if not np.isfinite(result[list(FEATURES)].to_numpy()).all():
            raise ValueError("Missing observed landmark features")
        result.to_parquet(path, index=False)
        receipt = {
            "world": entry["world"],
            "role": role,
            "anchors": len(result),
            "features": list(FEATURES),
            "sha256": sha256(path),
            "protocol_sha256": sha256(output / "protocol.json"),
            "source_prepared_sha256": entry["sha256"],
            "source_manifest_sha256": sha256(manifest),
        }
        write_json(receipt_path, receipt)
        frames.append(result)
        receipts.append(receipt)
        print(
            json.dumps(
                {
                    "event": "prepared",
                    "world": entry["world"],
                    "role": role,
                    "anchors": len(result),
                }
            ),
            flush=True,
        )
    write_json(output / f"{role}_data_audit.json", receipts)
    return pd.concat(frames, ignore_index=True)
