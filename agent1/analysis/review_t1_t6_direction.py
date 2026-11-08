"""Read-only feasibility diagnostics for the proposed weekly receipt process.

No model is trained. Existing v4/v5/v6 artifacts are read only. Run from the
repository root with .venv/Scripts/python.exe -B -m analysis.review_t1_t6_direction.
The output is diagnostic; it does not establish new-model skill or a release gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V6 = ROOT / "outputs/data/t1_competing_v6_20261101"
OUTPUT = ROOT / "outputs/analysis/t1_t6_direction_review_20261103"


def oracle_audit(output: Path) -> dict:
    """Compare true receipt cash with a true-settlement-date lump approximation.

    Both series cover only the saved evaluation anchors, not whole-company cash
    balances. The approximation is not a statistical lower bound on forecast error.
    """
    rows, fingerprints = [], {}
    for file in sorted((V6 / "evaluation_predictions").glob("*.parquet")):
        world = file.stem
        role = ("fresh_test" if world.startswith("v6_holdout") else
                "validation" if "_validation_" in world else "test")
        payment_file = ROOT / "data/synthetic" / world / "payments.parquet"
        for source in (file, payment_file):
            fingerprints[source.relative_to(ROOT).as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
        frame = pd.read_parquet(file)
        assert frame.invoice_id.is_unique
        payments = pd.read_parquet(payment_file, columns=["invoice_id", "pay_date_true", "amount", "kind"])
        receipts = payments.merge(frame[["invoice_id", "cutoff", "time_days", "cause"]],
                                  on="invoice_id", validate="many_to_one")
        receipts["day"] = (receipts.pay_date_true - receipts.cutoff).dt.days
        receipts = receipts[receipts.day.between(1, 91)].copy()
        receipts["week"] = (receipts.day - 1) // 7
        receipts["before_full"] = (receipts.cause != 1) | (receipts.day < receipts.time_days)
        actual = np.zeros((len(frame), 13))
        index = pd.Series(np.arange(len(frame)), index=frame.invoice_id)
        np.add.at(actual, (receipts.invoice_id.map(index).to_numpy(), receipts.week.to_numpy()),
                  receipts.amount.to_numpy())
        oracle = np.zeros_like(actual)
        paid = frame.cause.eq(1) & frame.time_days.between(1, 91)
        week = ((frame.loc[paid, "time_days"].to_numpy() - 1) // 7).astype(int)
        oracle[np.flatnonzero(paid.to_numpy()), week] = frame.loc[paid, "amount_open"].to_numpy()
        for horizon in (4, 13):
            a, b = actual[:, :horizon].sum(1), oracle[:, :horizon].sum(1)
            firm = frame.firm_id.to_numpy()
            totals = pd.DataFrame({"firm": firm, "actual": a, "oracle": b}).groupby("firm").sum()
            aw = pd.DataFrame(actual[:, :horizon]).assign(firm=firm).groupby("firm").sum().to_numpy()
            bw = pd.DataFrame(oracle[:, :horizon]).assign(firm=firm).groupby("firm").sum().to_numpy()
            ac, bc = np.cumsum(aw, axis=1), np.cumsum(bw, axis=1)
            before = receipts[receipts.day.le(7*horizon) & receipts.before_full]
            rows.append(dict(
                world=world, role=role, weeks=horizon, n=len(frame), actual_cash=float(a.sum()),
                oracle_full_settlement_cash=float(b.sum()),
                firm_abs_error=float(abs(totals.oracle-totals.actual).sum()),
                invoice_abs_error=float(abs(b-a).sum()),
                firm_week_abs_error=float(abs(bw-aw).sum()),
                firm_week_cumulative_abs_error=float(abs(bc-ac).sum()),
                actual_firm_week_cumulative_sum=float(ac.sum()),
                cash_before_full_settlement=float(before.amount.sum()),
                invoices_receiving_cash_before_full_settlement=int(before.invoice_id.nunique()),
                invoices_with_any_receipt=int((a > 0).sum()),
                overpredicted_invoices=int((b > a+1).sum()), underpredicted_invoices=int((a > b+1).sum()),
            ))
        print(f"receipt audit: {world}, {len(frame):,} anchors", flush=True)
    result = pd.DataFrame(rows)
    result.to_csv(output / "oracle_full_settlement_audit_by_world.csv", index=False)
    aggregate = result.groupby(["role", "weeks"], as_index=False).sum(numeric_only=True)
    for numerator, name in (("firm_abs_error", "firm_cumulative_wape"),
                            ("invoice_abs_error", "invoice_cumulative_wape"),
                            ("firm_week_abs_error", "firm_weekly_wape"),
                            ("cash_before_full_settlement", "cash_before_full_settlement_share")):
        aggregate[name] = aggregate[numerator] / aggregate.actual_cash
    aggregate["firm_cumulative_path_wape"] = aggregate.firm_week_cumulative_abs_error / aggregate.actual_firm_week_cumulative_sum
    aggregate["cash_bias"] = (aggregate.oracle_full_settlement_cash-aggregate.actual_cash) / aggregate.actual_cash
    aggregate.to_csv(output / "oracle_full_settlement_audit_summary.csv", index=False)
    reference = pd.read_csv(V6 / "cash_comparison.csv")
    reference = reference[reference.model.eq("v5_full_payment_proxy") & reference.day.isin([28, 91])].copy()
    reference["weeks"] = reference.day // 7
    joined = result.merge(reference[["world", "weeks", "actual_cash"]], on=["world", "weeks"],
                          suffixes=("_audit", "_saved"), validate="one_to_one")
    assert len(joined) == 12 and result[result.weeks.eq(13)].n.sum() == 65221
    np.testing.assert_allclose(joined.actual_cash_audit, joined.actual_cash_saved, rtol=0, atol=1)
    return dict(input_sha256=fingerprints, evaluation_anchors=65221,
                max_actual_cash_difference_from_saved=float(abs(joined.actual_cash_audit-joined.actual_cash_saved).max()))


def label_support(output: Path) -> dict:
    from experiments.t1_competing_v6.features import ReceiptIndex

    cohort = json.loads((ROOT / "data/synthetic/v4_shortpay_4shock_20261028_cohort.json").read_text(encoding="utf-8"))
    rows = []
    for entry in cohort["worlds"]:
        if entry["role"] != "train":
            continue
        world = entry["name"]
        frame = pd.read_parquet(V6 / "cache" / f"train_{world}.parquet")
        frame = frame[frame.partition.eq("fit")]
        payments = pd.read_parquet(ROOT / "data/synthetic" / world / "payments.parquet")
        amount = ReceiptIndex(payments).targets(frame, [7], "2024-07-01")[:, 0]
        remaining = frame.amount_open.to_numpy(float)
        state = np.where(frame.time_days.to_numpy() <= 7, frame.cause.to_numpy(), 0)
        bands = np.where(amount <= 1, "zero", np.where(amount >= remaining-1, "full", "partial"))
        rows.append(dict(world=world, anchors=len(frame), zero=int((bands == "zero").sum()),
                         partial=int((bands == "partial").sum()), full=int((bands == "full").sum()),
                         paid_terminal=int((state == 1).sum()), writeoff_terminal=int((state == 2).sum()),
                         credit_terminal=int((state == 3).sum()),
                         receipt_and_writeoff_same_week=int(((amount > 1) & (state == 2)).sum()),
                         receipts_exceed_start_balance=int((amount > remaining+1).sum())))
    result = pd.DataFrame(rows)
    result.to_csv(output / "train_one_week_label_support.csv", index=False)
    totals = result.sum(numeric_only=True).astype(int).to_dict()
    assert totals["anchors"] == 200000 and totals["receipts_exceed_start_balance"] == 0
    return totals


def reachable_label_support(output: Path) -> dict:
    """Count distinct invoice-weeks reachable from the existing fit anchors.

    This measures label support for 13-step training without adding new origins,
    firms or post-origin invoices. Repeated origins may still share the same event;
    counting distinct invoice-weeks avoids treating those as independent events.
    """
    cohort = json.loads((ROOT / "data/synthetic/v4_shortpay_4shock_20261028_cohort.json").read_text(encoding="utf-8"))
    origin, rows = pd.Timestamp("2019-04-01"), []
    for entry in cohort["worlds"]:
        if entry["role"] != "train":
            continue
        world = entry["name"]
        frame = pd.read_parquet(V6 / "cache" / f"train_{world}.parquet")
        frame = frame[frame.partition.eq("fit")]
        invoices = pd.read_parquet(ROOT / "data/synthetic" / world / "invoices.parquet").set_index("invoice_id")
        delta = (frame.cutoff-origin).dt.days
        assert delta.mod(7).eq(0).all()
        step = np.tile(np.arange(13), len(frame))
        pairs = pd.DataFrame({"invoice_id": np.repeat(frame.invoice_id.to_numpy(), 13),
                              "week": np.repeat((delta // 7).to_numpy(), 13)+step})
        pairs = pairs[np.repeat(frame.time_days.to_numpy(), 13) > step*7].drop_duplicates(["invoice_id", "week"])
        payments = pd.read_parquet(ROOT / "data/synthetic" / world / "payments.parquet",
                                  columns=["invoice_id", "pay_date_true", "amount"])
        payments["week"] = ((payments.pay_date_true-origin).dt.days-1) // 7
        receipts = payments.groupby(["invoice_id", "week"], as_index=False).amount.sum().sort_values(["invoice_id", "week"])
        receipts["cash_before"] = receipts.groupby("invoice_id").amount.cumsum()-receipts.amount
        receipts = receipts.merge(pairs, on=["invoice_id", "week"], validate="one_to_one")
        start = origin + pd.to_timedelta(receipts.week*7, unit="D")
        credit = receipts.invoice_id.map(invoices.credit_note).where(receipts.invoice_id.map(invoices.credit_note_date).le(start), 0)
        remaining = receipts.invoice_id.map(invoices.amount_gross)-credit-receipts.cash_before
        partial = (receipts.amount > 1) & (receipts.amount < remaining-1)
        rows.append(dict(world=world, fit_firms=frame.firm_id.nunique(), fit_anchors=len(frame),
                         unique_open_invoice_weeks=len(pairs), positive_receipt_invoice_weeks=len(receipts),
                         partial_receipt_invoice_weeks=int(partial.sum()),
                         unique_partial_invoices=int(receipts.loc[partial, "invoice_id"].nunique()),
                         full_receipt_invoice_weeks=int((receipts.amount >= remaining-1).sum()),
                         no_receipt_invoice_weeks=len(pairs)-len(receipts),
                         cash_exceeds_opening_balance=int((receipts.amount > remaining+1).sum())))
    result = pd.DataFrame(rows)
    result.to_csv(output / "train_reachable_13w_label_support.csv", index=False)
    totals = result.sum(numeric_only=True).astype(int).to_dict()
    assert totals["fit_anchors"] == 200000 and totals["cash_exceeds_opening_balance"] == 0
    return totals


def throughput_reference(output: Path) -> dict:
    """Optional reference only: does not time the new model or its simulator."""
    import lightgbm as lgb
    from experiments.t1_competing_v6.core import week_matrix

    metadata = json.loads((V6 / "train.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(V6 / "cache/train_v4_shortpay_4shock_20261028_train_000.parquet")
    matrix = week_matrix(frame, 1, metadata["features"])
    matrix = np.tile(matrix, (int(np.ceil(100000/len(matrix))), 1))[:100000]
    model = lgb.Booster(model_file=str(V6 / "model.txt"))
    model.predict(matrix[:1000], num_threads=4)
    elapsed = []
    for _ in range(3):
        start = time.perf_counter()
        predicted = model.predict(matrix, num_threads=4)
        elapsed.append(time.perf_counter()-start)
    median = float(np.median(elapsed))
    value = dict(benchmark_scope="existing v6 hazard model; not the proposed transition model",
                 rows=len(matrix), features=matrix.shape[1], classes=predicted.shape[1], threads=4,
                 seconds=elapsed, median_seconds=median,
                 naive_26m_rows_linear_projection_seconds=median*260,
                 one_week_2m_float32_feature_matrix_mib=2000000*matrix.shape[1]*4/1024**2,
                 excludes="feature updates, more classes, copula, reductions, early closure, grouping and caching")
    (output / "prediction_throughput_reference.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="rerun the optional existing-model throughput reference")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    checks = oracle_audit(OUTPUT)
    checks["one_week_training_labels"] = label_support(OUTPUT)
    checks["reachable_13w_training_labels"] = reachable_label_support(OUTPUT)
    if args.benchmark:
        checks["throughput_reference"] = throughput_reference(OUTPUT)
    checks["scope"] = "diagnostic audit, not a new model training or T6 end-to-end benchmark"
    (OUTPUT / "verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2), flush=True)


if __name__ == "__main__":
    main()
