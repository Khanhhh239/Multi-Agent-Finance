import numpy as np
import pandas as pd
from agent1.eval.promise_reliability import predict_week, resolved_history


def test_unresolved_late_verified_and_future_promises_do_not_change_prediction():
    p = pd.DataFrame(dict(customer_id=['c']*4, firm_id=['f']*4, kept=[True,False,False,False],
        made_date=pd.to_datetime(['2024-01-01','2024-01-09','2024-01-01','2025-01-01']),
        promised_date=pd.to_datetime(['2024-01-02','2024-01-10','2024-01-02','2025-01-02']),
        resolved_date=pd.to_datetime(['2024-01-05','2024-01-13','2024-02-01','2025-01-05'])))
    q = pd.DataFrame(dict(customer_id=['c','new'],firm_id=['f','f']))
    assert len(resolved_history(p,'2024-01-10')) == 1
    full, prefix = predict_week(p,q,'2024-01-10'), predict_week(p.iloc[:1],q,'2024-01-10')
    for name in full:
        np.testing.assert_allclose(full[name],prefix[name])
        assert np.isfinite(full[name]).all()
    np.testing.assert_allclose(full['Customer historical rate'],[1.,5/7])


def test_query_outcomes_never_enter_predictions_and_order_is_preserved():
    p = pd.DataFrame(dict(customer_id=['a','b'], firm_id=['f','f'], kept=[True,False],
        made_date=pd.to_datetime(['2024-01-01']*2),promised_date=pd.to_datetime(['2024-01-02']*2)))
    q = pd.DataFrame(dict(customer_id=['b','a'],firm_id=['f','f'],kept=[True,False]),index=[12,8])
    first = predict_week(p,q,'2024-01-10'); second = predict_week(p,q.assign(kept=~q.kept),'2024-01-10')
    for name in first: np.testing.assert_allclose(first[name],second[name])
    np.testing.assert_allclose(first['Customer historical rate'],[0,1])
