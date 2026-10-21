import pandas as pd
from agent1.models.dispute_features import at_issue_dispute_rates, add_dispute_rates


def test_dispute_rate_frozen_at_issue_uses_only_previous_closed_invoices():
    inv = pd.DataFrame(dict(invoice_id=['a','b','future'], firm_id=['f']*3,customer_id=['c']*3,
        issue_date=pd.to_datetime(['2024-01-01','2024-01-10','2025-01-01']),
        paid_date_true=pd.to_datetime(['2024-01-05','2024-02-01','2025-01-10']),
        writeoff_date=pd.to_datetime([None]*3),amount_gross=[100.,100.,100.],
        dispute=[True,True,False],partial=[False]*3,days_late_true=[1.,2.,0.]))
    rates = at_issue_dispute_rates(inv)
    assert rates['a'] == .02
    assert rates['b'] == (1+.02*20)/21
    changed = inv.copy(); changed.loc[1:,'dispute'] = False
    pd.testing.assert_series_equal(rates.loc[['a','b']],at_issue_dispute_rates(changed).loc[['a','b']])
    query = pd.DataFrame(dict(invoice_id=['b','a'],cutoff=pd.to_datetime(['2024-03-01']*2)))
    result = add_dispute_rates(query,rates)
    assert result.c_disp_eb.tolist() == [rates['b'],rates['a']]
    assert 'c_disp_eb' not in query
