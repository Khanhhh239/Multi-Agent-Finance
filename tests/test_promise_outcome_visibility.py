import pandas as pd
from agent1.models.features import SnapshotBuilder
from agent1.models.features import FEATURES
from test_features import invoices


def test_unresolved_promise_is_visible_but_not_counted_as_a_failure():
    inv=invoices()
    promises=pd.DataFrame({'invoice_id':['o1'],'customer_id':['c'],
        'made_date':pd.to_datetime(['2023-03-01']),'promised_date':pd.to_datetime(['2023-03-05']),'kept':[None]})
    result=SnapshotBuilder(inv,promises=promises).snapshot('2023-03-20')
    row=result[result.invoice_id=='o1'].iloc[0]
    assert row.has_promise==1 and row.c_promise_n==0
    assert row.c_promise_rel==4/6


def test_future_only_promise_table_is_as_invisible_as_no_promises():
    inv=invoices();inv['invoice_id']=inv.invoice_id.astype('string[pyarrow]')
    promises=pd.DataFrame(dict(invoice_id=['o1'],customer_id=['c'],made_date=pd.to_datetime(['2024-01-01']),
        promised_date=pd.to_datetime(['2024-01-10']),kept=[True]))
    plain=SnapshotBuilder(inv).snapshot('2023-03-20')
    with_future=SnapshotBuilder(inv,promises=promises).snapshot('2023-03-20')
    pd.testing.assert_frame_equal(plain[FEATURES],with_future[FEATURES])
