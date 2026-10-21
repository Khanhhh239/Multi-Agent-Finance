import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from agent1_service.api import create_app
from agent1.models.t6_cash import simulate


def test_service_expense_scenario_conserves_cash_and_rejects_unknown_customer(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT1_RESEARCH_MODE','1')
    def engine(*_):
        frame=pd.DataFrame(dict(invoice_id=['i'],customer_id=['c'],amount_open=[1000.]))
        pmf=np.zeros((1,13));pmf[0,0]=1.
        args=dict(open_df=frame,P=pmf,B0=0.,known_out=np.full(13,100.),rev_q=None,kernel=np.zeros(17),capex_rate=0.,capex_sizes=[],n=30,seed=7)
        balances,_=simulate(**args)
        result=dict(cutoff='2024-07-01',band=[dict(week=i+1,P10=v,P50=v,P90=v) for i,v in enumerate(balances[0])],
            shortfall_4w=0.,shortfall_13w=1.,collections=[],review_count=0,seconds=0.)
        return result,args
    app=create_app(tmp_path,token='secret',engine=engine)
    headers={'Authorization':'Bearer secret'}
    tables={
        'invoices':[dict(invoice_id='i',customer_id='c',invoice_no='1',issue_date='2024-01-01',due_date='2024-02-01',amount_gross=1000)],
        'bank_txns':[dict(txn_id='t',value_date='2024-02-01',amount=1000,memo='i')],
        'customers':[dict(customer_id='c',short='C')],
        'outflows':[dict(date='2024-07-01',amount=100,category='rent')],
    }
    with TestClient(app) as client:
        for table,records in tables.items():
            assert client.post('/ingest',headers=headers,json=dict(table=table,records=records)).status_code==200
        base=client.post('/forecast',headers=headers,json=dict(cutoff='2024-06-30T18:00:00Z',balance=0))
        assert base.status_code==200
        scenario=client.post('/whatif',headers=headers,json=dict(shift_out=dict(from_week=1,to_week=2,amount=50)))
        assert scenario.status_code==200
        q=np.asarray(scenario.json()['quantiles'])
        assert q[0,1]==950 and q[1,1]==800 and q[-1,1]==-300
        assert client.post('/whatif',headers=headers,json=dict(shift_out=dict(from_week=1,to_week=2,amount=101))).status_code==422
        assert client.post('/whatif',headers=headers,json=dict(delay_customer='unknown')).status_code==422
        assert client.post('/whatif',headers=headers,json={}).status_code==422
