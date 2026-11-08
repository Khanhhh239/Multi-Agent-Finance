import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models.t9_fast import corroborated, reconcile_arrays  # noqa: E402


def test_memo_number_corroborates():
    assert corroborated(pd.Series({'name_score': 10}), {1234}, [1234, 99])


def test_name_corroborates():
    assert corroborated(pd.Series({'name_score': 95}), set(), [7])


def test_neither_does_not_corroborate():
    assert not corroborated(pd.Series({'name_score': 60}), {5}, [7])
    assert not corroborated(pd.Series({}), set(), [7])


def test_guard_threshold_must_be_at_least_tau():
    try:
        reconcile_arrays(None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), tau_auto=.8, corroborate_below=.5)
    except ValueError:
        return
    raise AssertionError('expected ValueError')


def _fifo_case():
    inv = pd.DataFrame(dict(invoice_id=['A', 'B', 'C'], firm_id='F', customer_id='c1', invoice_no=['11', '12', '13'],
                            issue_date=pd.to_datetime(['2024-01-01'] * 3),
                            due_date=pd.to_datetime(['2024-02-01', '2024-03-01', '2024-04-01']), amount_gross=[100e6, 100e6, 100e6]))
    bank = pd.DataFrame(dict(txn_id=['t1'], firm_id='F', value_date=pd.to_datetime(['2024-02-05']), amount=[150e6],
                             memo=[''], direction=['in']))
    assignments = pd.DataFrame(dict(txn_id=['t1'], customer_id=['c1'], confidence=[.99], name_score=[95.]))
    return inv, bank, assignments


def test_fifo_allocation_pays_oldest_first_with_partial_last():
    inv, bank, a = _fifo_case()
    links, _ = reconcile_arrays(None, bank, inv, None, tau_auto=.5, assignments=a, fifo_allocation=True)
    assert list(links.invoice_id) == ['A', 'B'] and list(links.kind) == ['full', 'partial']
    assert set(links.method) == {'fifo_allocation'} and links.amount.sum() == 150e6


def test_fifo_off_by_default_and_capped_subset_goes_to_review():
    inv, bank, a = _fifo_case()
    assert reconcile_arrays(None, bank, inv, None, tau_auto=.5, assignments=a)[0].empty
    links, queue = reconcile_arrays(None, bank, inv, None, tau_auto=.5, assignments=a, fifo_allocation=True, max_guess_subset=1)
    assert links.empty and queue.reason.tolist() == ['large_guess_subset']
