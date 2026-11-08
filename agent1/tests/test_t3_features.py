import pandas as pd
from agent1.models.t3_features import FEATURES, issue_features


def invoices():
    return pd.DataFrame(dict(invoice_id=['a','b','c'], firm_id=['f']*3, customer_id=['c']*3,
        issue_date=pd.to_datetime(['2024-01-01','2024-02-01','2025-01-01']), amount_gross=[10.,20.,100.],
        paid_date_true=pd.to_datetime(['2024-03-01','2024-04-01','2025-03-01']),
        writeoff_date=[pd.NaT]*3, days_late_true=[1,2,3], dispute=[True,False,True],
        partial=[False,True,True], term_days=[30]*3))


def test_future_amount_and_unresolved_outcomes_do_not_change_issue_features():
    inv = invoices()
    original = issue_features(inv).set_index('invoice_id')
    inv.loc[2,'amount_gross'] = 1e12
    inv.loc[:1,['dispute','partial','days_late_true']] = [False,False,0]
    changed = issue_features(inv).set_index('invoice_id')
    pd.testing.assert_frame_equal(original.loc[['a','b'],FEATURES],changed.loc[['a','b'],FEATURES])
    assert original.loc['b','c_n'] == 0
    assert original.loc['c','c_n'] == 2


def test_same_day_amount_scale_does_not_depend_on_input_order():
    inv = invoices()
    inv.loc[1,'issue_date'] = inv.loc[0,'issue_date']
    one = issue_features(inv).set_index('invoice_id')[FEATURES].sort_index()
    two = issue_features(inv.iloc[::-1]).set_index('invoice_id')[FEATURES].sort_index()
    pd.testing.assert_frame_equal(one,two)
