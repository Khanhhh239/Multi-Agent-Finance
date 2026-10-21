import numpy as np
import pandas as pd
from agent1.models.adaptive_features import AdaptiveSnapshotBuilder


def test_fast_features_ignore_future_settlements_and_future_invoices():
    inv=pd.DataFrame(dict(invoice_id=list('abcd'),firm_id=['f']*4,customer_id=['c']*4,
        issue_date=pd.to_datetime(['2023-01-01','2023-02-01','2023-03-01','2024-01-01']),
        due_date=pd.to_datetime(['2023-01-10','2023-02-10','2023-07-01','2024-02-01']),
        paid_date_true=pd.to_datetime(['2023-01-20','2023-06-29','2023-07-15',None]),amount_gross=[100.]*4))
    one=AdaptiveSnapshotBuilder(inv).snapshot('2023-07-01')
    changed=inv.copy();changed.loc[2,'paid_date_true']=pd.Timestamp('2025-01-01');changed.loc[3,'amount_gross']=1e12
    two=AdaptiveSnapshotBuilder(changed).snapshot('2023-07-01')
    columns=['f_resid_7d','c_delay_ewm','log_amount_rel']
    np.testing.assert_allclose(one[columns],two[columns])
    assert np.isfinite(one.f_resid_7d).all() and one.f_resid_7d.iloc[0]>0
