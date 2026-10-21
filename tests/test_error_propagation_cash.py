import numpy as np
import pandas as pd
from scripts.run_t9_t1_propagation import realized_cash


def test_cash_scoring_excludes_future_invoices_and_cutoff_day_and_keeps_partials():
    T=pd.Timestamp('2024-07-01')
    invoices=pd.DataFrame(dict(invoice_id=['known','future'],firm_id=['f','f'],issue_date=pd.to_datetime(['2024-06-01','2024-07-02'])))
    pay=pd.DataFrame(dict(invoice_id=['known','known','future','known'],
        pay_date_true=pd.to_datetime(['2024-07-02','2024-07-08','2024-07-03','2024-07-01']),amount=[2.,3.,100.,999.]))
    result=realized_cash(invoices,pay,[T],['f'])[T]
    expected=np.zeros((1,13));expected[0,0]=5.
    np.testing.assert_array_equal(result,expected)
