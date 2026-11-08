import numpy as np
import pandas as pd
import pytest
from agent1.eval.cash_cohort import forecast_pmf,validate_cash_cohort
from agent1.models.t6_cash import simulate


def test_no_open_ar_still_has_cash_forecast_and_shortfall():
    class Unused:
        def hazards(self,_):raise AssertionError('Không gọi T1 trên cohort rỗng')
    frame=pd.DataFrame({'invoice_id':[],'amount_open':[]})
    samples,_=simulate(frame,forecast_pmf(Unused(),frame),B0=10.,known_out=np.full(13,2.),
        rev_q=None,kernel=np.zeros(17),capex_rate=0.,capex_sizes=[],n=5)
    np.testing.assert_array_equal(samples,np.tile(10.-2*np.arange(1,14),(5,1)))
    assert (samples[:,-1]<0).all()


def test_full_cash_cohort_rejects_missing_empty_week():
    frame=pd.DataFrame([dict(firm_id='F',cutoff=cut,model='m',k=k) for cut in ['2024-01-01','2024-01-08'] for k in range(1,14)])
    validate_cash_cohort(frame,1,2,1)
    with pytest.raises(ValueError):validate_cash_cohort(frame.iloc[13:],1,2,1)
