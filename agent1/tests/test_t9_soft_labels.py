import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models.t9_soft_labels import soft_fifo_labels  # noqa: E402

M = 1e6


def _case():
    inv = pd.DataFrame(dict(invoice_id=["A", "B", "C"], firm_id="F", customer_id="c1",
                            issue_date=pd.to_datetime(["2024-01-01"] * 3),
                            due_date=pd.to_datetime(["2024-02-01", "2024-03-01", "2024-04-01"]), amount_gross=[100 * M, 100 * M, 100 * M]))
    bank = pd.DataFrame(dict(txn_id=["t1", "t2"], firm_id="F", value_date=pd.to_datetime(["2024-02-05", "2024-03-10"]),
                             amount=[150 * M, 150 * M], direction="in"))
    asg = pd.DataFrame(dict(txn_id=["t1", "t2"], customer_id="c1", confidence=[0.99, 0.99]))
    return inv, bank, asg


def test_fifo_labels_by_due_date_when_no_links():
    inv, bank, asg = _case()
    out = soft_fifo_labels(pd.DataFrame(columns=["txn_id", "invoice_id", "amount", "est_pay_date"]), bank, inv, asg)
    # t1 (150) tất toán A (100) + một phần B; t2 (150) tất toán B (còn 50) + C (100)
    assert out["A"] == pd.Timestamp("2024-02-05")
    assert out["B"] == pd.Timestamp("2024-03-10") and out["C"] == pd.Timestamp("2024-03-10")


def test_does_not_override_t9_links_and_uses_only_leftover():
    inv, bank, asg = _case()
    links = pd.DataFrame(dict(txn_id=["t1"], invoice_id=["A"], amount=[100 * M], est_pay_date=pd.to_datetime(["2024-02-05"])))
    out = soft_fifo_labels(links, bank, inv, asg)
    assert "A" not in out.index                      # đã có nhãn T9
    # t1 còn dư 50 → B mới được trả 50; t2 (150) trả nốt 50 của B rồi 100 của C ⇒ cả hai tất toán ở t2 (10/03)
    assert out["B"] == pd.Timestamp("2024-03-10") and out["C"] == pd.Timestamp("2024-03-10")


def test_low_confidence_and_future_invoices_are_skipped():
    inv, bank, asg = _case()
    low = asg.assign(confidence=0.2)
    assert soft_fifo_labels(pd.DataFrame(columns=["txn_id", "invoice_id", "amount", "est_pay_date"]), bank, inv, low).empty
    late = inv.assign(issue_date=pd.to_datetime(["2025-01-01"] * 3))                 # phát hành sau giao dịch ⇒ không dùng
    assert soft_fifo_labels(pd.DataFrame(columns=["txn_id", "invoice_id", "amount", "est_pay_date"]), bank, late, asg).empty


def test_ledger_cleared_invoices_do_not_absorb_cash():
    inv, bank, asg = _case()
    inv = inv.assign(ledger_clear_date=[pd.Timestamp("2024-01-20"), pd.NaT, pd.NaT])     # A đã đóng trong sổ trước giao dịch đầu
    out = soft_fifo_labels(pd.DataFrame(columns=["txn_id", "invoice_id", "amount", "est_pay_date"]), bank, inv, asg)
    assert "A" not in out.index
    assert out["B"] == pd.Timestamp("2024-02-05")        # t1 (150) tất toán B (100) và một phần C
