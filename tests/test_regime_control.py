import numpy as np
import pandas as pd
import pytest
from agent1.eval.regime_control import payment_residual,PortfolioCUSUM,DelayedACI,remove_common_customer_residual


def test_weekly_residual_cannot_be_read_before_its_reveal_date():
    frame=pd.DataFrame(dict(cutoff=pd.to_datetime(['2024-01-01']*3),
        label_date=pd.to_datetime(['2024-01-05','2024-02-01',None])))
    with pytest.raises(ValueError,match='chưa'):payment_residual(frame,[.2,.3,.1],'2024-01-07')
    full=payment_residual(frame,[.2,.3,.1],'2024-01-08')
    frame.loc[1,'label_date']=pd.Timestamp('2025-01-01')
    assert payment_residual(frame,[.2,.3,.1],'2024-01-08')==full


def test_delayed_aci_updates_only_matured_horizon_and_cusum_prefix_is_stable():
    state=DelayedACI();state.add('2024-01-01',0,0.,1.,2.);state.add('2024-01-01',12,0.,1.,100.)
    state.reveal('2024-01-07');np.testing.assert_allclose(state.aci.a,.2)
    state.reveal('2024-01-08');assert state.aci.a[0]<.2 and state.aci.a[12]==.2
    dates=pd.date_range('2024-01-01',periods=20,freq='7D');z=np.r_[np.zeros(5),np.full(15,3.)]
    full=PortfolioCUSUM();prefix=PortfolioCUSUM()
    one=[full.update(t,x) for t,x in zip(dates,z)]
    two=[prefix.update(t,x) for t,x in zip(dates[:10],z[:10])]
    assert one[:10]==two


def test_common_shock_is_removed_without_using_customer_own_outcome_as_peer():
    frame=pd.DataFrame(dict(firm_id=['f']*3,date=pd.to_datetime(['2024-01-01']*3),
        customer_id=['a','b','c'],residual=[3.,3.,3.],weight=[1.,1.,1.]))
    np.testing.assert_allclose(remove_common_customer_residual(frame).conditional_residual,0.)
    frame.loc[0,'residual']=7.
    result=remove_common_customer_residual(frame)
    assert result.common_from_other_customers.iloc[0]==3. and result.conditional_residual.iloc[0]==4.
