import pandas as pd
from scripts.run_e2e_protocol import observed_promises


def test_promise_outcome_uses_only_estimated_cash_before_grace_period():
    invoices=pd.DataFrame(dict(invoice_id=['a','b'],amount_gross=[10000.,100000.]))
    promises=pd.DataFrame(dict(invoice_id=['a','b','b'],promised_date=pd.to_datetime(['2024-01-10']*3),
        promised_fraction=[1.,.5,1.],kept=[True,False,True]))
    links=pd.DataFrame(dict(invoice_id=['b','b'],est_pay_date=pd.to_datetime(['2024-01-12','2024-02-01']),amount=[50000.,50000.]))
    result=observed_promises(promises,invoices,links)
    assert result.kept.tolist()==[False,True,False]
    pd.testing.assert_frame_equal(result,observed_promises(promises.assign(kept=False),invoices,links))
def test_diagnostic_e2e_does_not_overwrite_full_evidence():
    from scripts.run_e2e_protocol import protocol_output
    assert protocol_output('tgt',None,52).name=='e2e'
    assert protocol_output('tgt',['F000'],2)!=protocol_output('tgt',None,52)
    assert 'diagnostics' in protocol_output('tgt',['F000'],2).parts

