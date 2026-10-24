import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models.t9_review_queue import queued_transactions, simulate_review  # noqa: E402

M = 1e6
COLS = ["txn_id", "invoice_id", "est_pay_date", "kind", "amount", "method", "confidence"]


def _case():
    bank = pd.DataFrame(dict(txn_id=["t1", "t2", "t3", "t4"], firm_id="F", direction="in",
                             value_date=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-10"]),
                             amount=[50 * M, 300 * M, 100 * M, 80 * M]))
    links = pd.DataFrame([["t3", "C", pd.Timestamp("2024-01-04"), "full", 100 * M, "R2_memo", 1.0]], columns=COLS)
    truth = pd.DataFrame(dict(txn_id=["t1", "t2", "t2", "t3", "t4"], invoice_id=["A", "B1", "B2", "C", "D"],
                              amount=[50 * M, 100 * M, 200 * M, 100 * M, 80 * M],
                              pay_date_true=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-03", "2024-01-04", "2024-01-10"])))
    return bank, links, truth


def test_queue_is_unlinked_cash_only():
    bank, links, _ = _case()
    assert set(queued_transactions(links, bank).txn_id) == {"t1", "t2", "t4"}


def test_leftover_policy_reviews_largest_first_within_weekly_budget():
    bank, links, truth = _case()
    out, stats = simulate_review(links, bank, truth, per_week=1, policy="leftover")
    # tuần 1 (t1, t2): duyệt t2 (300); tuần 2: t4 (80) cạnh tồn t1 (50) ⇒ duyệt t4
    assert set(out[out.method == "human_review"].txn_id) == {"t2", "t4"}
    assert stats["n_reviewed"] == 2 and set(out[out.txn_id == "t2"].invoice_id) == {"B1", "B2"}
    assert "C" in set(out.invoice_id)                       # liên kết T9 có sẵn giữ nguyên


def test_zero_budget_changes_nothing():
    bank, links, truth = _case()
    out, stats = simulate_review(links, bank, truth, per_week=0)
    assert out.equals(links) and stats["n_reviewed"] == 0
