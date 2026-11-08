import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_t6 import known_outflows,weekly


def test_weekly_boundary_does_not_double_count_snapshot_day():
    s=pd.Series([100.,200.,300.],index=pd.to_datetime(['2024-07-01','2024-07-02','2024-07-08']))
    assert weekly(s,pd.Timestamp('2024-07-01'))[0]==500


def test_unannounced_future_tax_and_utility_amounts_do_not_leak():
    T=pd.Timestamp('2024-07-01')
    g=pd.DataFrame({'date':pd.to_datetime(['2024-05-20','2024-06-20','2024-08-20']),
                    'category':['vat']*3,'amount':[100.,100.,999999.]})
    empty=pd.Series(dtype=float,index=pd.DatetimeIndex([]))
    one=known_outflows(dict(known=empty,sup=empty,scheduled=g),T)
    g.loc[2,'amount']=123456789.
    two=known_outflows(dict(known=empty,sup=empty,scheduled=g),T)
    np.testing.assert_array_equal(one,two)
