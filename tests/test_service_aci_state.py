"""/forecast lưu và đọc lại trạng thái ACI theo doanh nghiệp (dải công bố = copula-t + ACI)."""
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import agent1_service.api as service_api
from agent1_service.jobs import aci_band
from agent1.models.t6_cash import K


def test_forecast_persists_aci_state_between_calls(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_RESEARCH_MODE', '1')
    seen = []

    def engine(invoices, bank, customers, promises, outflows, cutoff, balance, *, model_cache=None, aci_state=None):
        seen.append(aci_state)
        samples = np.random.default_rng(0).normal(balance, 10, (500, K))
        state, aci = aci_band.update(aci_state, cutoff, balance)
        rows, meta = aci_band.band(state, aci, cutoff, samples)
        frame = pd.DataFrame(dict(invoice_id=['i'], customer_id=['c'], amount_open=[1000.]))
        result = dict(cutoff=cutoff, band=rows, shortfall_4w=0., shortfall_13w=0., collections=[], review_count=0,
                      seconds=0., aci_state=state, **meta)
        return result, dict(open_df=frame)

    monkeypatch.setattr(service_api, 'run', engine)
    app = service_api.create_app(tmp_path, token='secret', engine=engine)
    headers = {'Authorization': 'Bearer secret'}
    tables = {
        'invoices': [dict(invoice_id='i', customer_id='c', invoice_no='1', issue_date='2024-01-01', due_date='2024-02-01', amount_gross=1000)],
        'bank_txns': [dict(txn_id='t', value_date='2024-02-01', amount=1000, memo='i')],
        'customers': [dict(customer_id='c', short='C')],
        'outflows': [dict(date='2024-07-01', amount=100, category='rent')],
    }
    with TestClient(app) as client:
        for table, records in tables.items():
            assert client.post('/ingest', headers=headers, json=dict(table=table, records=records)).status_code == 200
        first = client.post('/forecast', headers=headers, json=dict(cutoff='2024-07-01', balance=100))
        assert first.status_code == 200, first.text
        body = first.json()
        assert body['band_method'] == 'copula-t+ACI' and body['aci_ready'] is False and 'aci_state' not in body
        second = client.post('/forecast', headers=headers, json=dict(cutoff='2024-07-08', balance=50))
        assert second.status_code == 200, second.text
    assert seen[0] == {}                                   # lần đầu: trạng thái rỗng
    assert len(seen[1]['pending']) == K                    # lần hai: đọc lại khoảng đã ghi ở lần đầu
    assert '2024-07-01' in seen[1]['balances']
