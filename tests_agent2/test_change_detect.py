"""Causality and correctness of change_detect (dữ liệu tổng hợp)."""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent2.change_detect import CD_FEATURES, EntityDeviation2, change_features

COLS = ["transaction_id", "company_id", "posted_at", "txn_type", "amount_vnd", "unit_price_vnd", "vendor_id",
        "customer_id", "employee_id", "creator_id", "invoice_id", "applied_invoice_id", "collector_id", "advance_id"]


def write_world(path: Path, rows):
    path.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{c: r.get(c, "") for c in COLS} for r in rows])
    frame.to_csv(path / "transactions.csv", index=False)
    pd.DataFrame([{"company_id": "C1", "customer_terms_days": "30"}]).to_csv(path / "companies.csv", index=False)
    return frame


def pay(i, day, amount, emp="E1", creator="K1"):
    return dict(transaction_id=f"T{i:05d}", company_id="C1", posted_at=f"{day}T10:00:00+07:00", txn_type="payroll",
                amount_vnd=str(amount), employee_id=emp, creator_id=creator)


def test_payroll_level_matches_bruteforce_and_ignores_second_rows(tmp_path):
    months = ["2024-01-25", "2024-02-26", "2024-03-25", "2024-04-25", "2024-05-27", "2024-06-25", "2024-07-25"]
    base = [10_000_000, 10_100_000, 9_900_000, 10_000_000, 10_200_000, 10_000_000, 11_500_000]
    rows = [pay(k, d, a) for k, (d, a) in enumerate(zip(months, base))]
    rows.append(pay(99, "2024-06-28", 30_000_000))           # bonus: second row of June
    f = change_features(write_world(tmp_path / "w", rows).pipe(lambda _: tmp_path / "w")).set_index("transaction_id")
    firsts = [math.log(a) for a in base]
    expected = firsts[6] - float(np.median(firsts[:6]))
    assert f.loc["T00006", "pay_lr"] == pytest.approx(expected, abs=1e-5)
    assert f.loc["T00099", "pay_lr"] == 0                      # second row of a month is not scored
    assert f.loc["T00002", "pay_lr"] == 0                      # fewer than three earlier months


def test_prefix_invariance_on_generated_world(tmp_path):
    world = Path("work/data/v5dev_smoke1099")
    if not (world / "transactions.csv").exists():
        pytest.skip("smoke world not generated on this machine")
    tx = pd.read_csv(world / "transactions.csv", dtype=str, keep_default_na=False)
    full = change_features(world).set_index("transaction_id")
    cut = sorted(tx.posted_at)[len(tx) * 2 // 3]
    part = tmp_path / "prefix"
    part.mkdir()
    tx[tx.posted_at < cut].to_csv(part / "transactions.csv", index=False)
    (part / "companies.csv").write_bytes((world / "companies.csv").read_bytes())
    early = change_features(part).set_index("transaction_id")
    pd.testing.assert_frame_equal(early[CD_FEATURES], full.loc[early.index, CD_FEATURES])


def test_rows_sharing_a_timestamp_do_not_see_each_other(tmp_path):
    rows = [pay(k, f"2024-0{k + 1}-25", 10_000_000) for k in range(4)]
    rows += [pay(10, "2024-05-25", 12_000_000, emp="E1"), pay(11, "2024-05-25", 12_000_000, emp="E2")]
    rows += [pay(20 + k, f"2024-0{k + 1}-25", 10_000_000, emp="E2") for k in range(4)]
    f = change_features(write_world(tmp_path / "w", rows).pipe(lambda _: tmp_path / "w")).set_index("transaction_id")
    # both movers posted at the same time: neither counts the other as an earlier group mover
    assert f.loc["T00010", "grp_pay_up_n"] == 0 and f.loc["T00011", "grp_pay_up_n"] == 0


def test_time_windows_use_real_days_and_receivables_age(tmp_path):
    """Regression: pandas 3 stores parsed datetimes in ms; windows must still be measured in days."""
    rows = [dict(transaction_id=f"T{m:04d}", company_id="C1", posted_at=f"2024-{m:02d}-10T10:00:00+07:00",
                 txn_type="cash_withdrawal", amount_vnd="5000000") for m in range(1, 9)]
    rows += [dict(transaction_id=f"T005{k}", company_id="C1", posted_at=f"2024-08-{20 + 2 * k}T10:00:00+07:00",
                  txn_type="cash_withdrawal", amount_vnd="5000000") for k in range(2)]
    rows += [dict(transaction_id="T0060", company_id="C1", posted_at="2024-01-05T10:00:00+07:00", txn_type="sales_invoice",
                  amount_vnd="1000000", customer_id="U1", creator_id="S1", invoice_id="I1"),
             dict(transaction_id="T0061", company_id="C1", posted_at="2024-05-05T10:00:00+07:00", txn_type="sales_invoice",
                  amount_vnd="1000000", customer_id="U1", creator_id="S1", invoice_id="I2")]
    f = change_features(write_world(tmp_path / "w", rows).pipe(lambda _: tmp_path / "w")).set_index("transaction_id")
    assert f.loc["T0051", "rec_excess"] > f.loc["T0008", "rec_excess"]       # three withdrawals inside 35 days
    assert f.loc["T0061", "ar_cust_overdue_n"] == 1                            # I1 open 121 days, terms 30
    assert f.loc["T0061", "ar_mgr_overdue_share"] == 1.0


def test_customer_discount_is_a_left_tail(tmp_path):
    rows = []
    for k in range(12):
        rows.append(dict(transaction_id=f"T{k:05d}", company_id="C1", posted_at=f"2024-{k % 12 + 1:02d}-10T10:00:00+07:00",
                         txn_type="sales_invoice", amount_vnd=str(20_000_000 + 300_000 * (k % 3)), customer_id="U1",
                         creator_id="S1", invoice_id=f"I{k}"))
    rows.append(dict(transaction_id="T00099", company_id="C1", posted_at="2024-12-20T10:00:00+07:00",
                     txn_type="sales_invoice", amount_vnd="12000000", customer_id="U1", creator_id="S1", invoice_id="I99"))
    frame = change_features(write_world(tmp_path / "w", rows).pipe(lambda _: tmp_path / "w"))
    kinds = np.array(["sales_invoice"] * len(frame))
    ed = EntityDeviation2()
    ed.fit(pd.concat([frame] * 3, ignore_index=True), np.array(list(kinds) * 3))   # enough reference points
    parts = ed.parts(frame, kinds)
    row = frame.index[frame.transaction_id == "T00099"][0]
    assert frame.loc[row, "cust_z"] < -3
    assert parts["cust_z-"][row] > parts["cust_z+"][row]
