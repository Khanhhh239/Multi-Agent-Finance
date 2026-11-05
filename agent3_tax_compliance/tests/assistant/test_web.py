"""HTTP layer of the local app: workspaces, uploads, decisions, pack invariants, law endpoints. No network, no model."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.assistant import web
from src.lawbase import sync as lawsync


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    monkeypatch.setattr(web, 'LAW_DB', tmp_path / 'law' / 'corpus.sqlite3')
    monkeypatch.setattr(web, '_as_of', lambda ws: __import__('datetime').date(2026, 10, 15))
    return TestClient(web.app)


def test_demo_run_report_and_not_claimed_decision(client):
    wid = client.post('/api/demo').json()['id']
    assert [w['id'] for w in client.get('/api/workspaces').json()] == [wid]
    rep = client.post(f'/api/workspaces/{wid}/run').json()
    assert rep['totals']['at_risk_invoices'] > 0
    assert client.get(f'/api/workspaces/{wid}/report').json()['totals'] == rep['totals']
    dup = next(it for it in rep['items'] if it['code'] == 'R05_DUPLICATE')
    bad = client.post(f'/api/workspaces/{wid}/decisions', json=dict(invoice_key=dup['invoice_keys'][0], action='IGNORE', evidence='x', by='y'))
    assert bad.status_code == 422
    ok = client.post(f'/api/workspaces/{wid}/decisions', json=dict(invoice_key=dup['invoice_keys'][0], action='NOT_CLAIMED',
                                                                  evidence='Bản trùng', by='Kế toán trưởng')).json()
    assert float(ok['totals']['at_risk_vat']) < float(rep['totals']['at_risk_vat'])


def test_pack_can_only_tighten(client):
    wid = client.post('/api/demo').json()['id']
    pack = client.get(f'/api/workspaces/{wid}/pack').json()
    pack['thresholds'] = dict(match_days_after_invoice=400)
    r = client.put(f'/api/workspaces/{wid}/pack', json=pack)
    assert r.status_code >= 400
    pack['thresholds'] = dict(match_days_after_invoice=30)
    assert client.put(f'/api/workspaces/{wid}/pack', json=pack).status_code == 200


def test_profile_is_validated_against_the_input_schema(client):
    bad = dict(tax_code='0109999982', legal_name='Công ty thử', vat_method='KHAU_TRU', filing_period='MONTH')
    r = client.post('/api/workspaces', json=dict(profile=bad))
    assert r.status_code == 422 and 'phương pháp' in r.json()['detail']
    assert client.post('/api/workspaces', json=dict(profile=dict(bad, vat_method='DEDUCTION', tax_code='0109999981'))).status_code == 422
    assert not (web.WORKSPACES / '0109999982').exists()          # a rejected profile leaves nothing behind


def test_uploads_are_checked(client):
    wid = client.post('/api/workspaces', json=dict(profile=dict(tax_code='0109999982', legal_name='Công ty thử', vat_method='DEDUCTION',
                                                                 filing_period='MONTH'))).json()['id']
    assert client.put(f'/api/workspaces/{wid}/files/purchase_xml?name=a.exe', content=b'x').status_code == 415
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('../../escape.xml', '<x/>')
    r = client.put(f'/api/workspaces/{wid}/files/purchase_xml?name=hd.zip', content=buf.getvalue())
    assert r.status_code == 200 and r.json()['saved'] == ['escape.xml']          # paths flattened: nothing lands outside
    assert not (web.WORKSPACES / 'escape.xml').exists() and not (web.WORKSPACES.parent / 'escape.xml').exists()
    r = client.put(f'/api/workspaces/{wid}/files/purchase_xml?name=../../hd%201.xml', content=b'<HDon/>')
    assert r.status_code == 200 and r.json()['saved'] == ['hd_1.xml']
    assert client.get(f'/api/workspaces/{wid}/files/purchase_xml').json() == ['escape.xml', 'hd_1.xml']
    assert client.get('/api/workspaces/..%2Fetc/pack').status_code in (400, 404)


def test_law_endpoints_without_corpus_and_with_a_running_sync(client):
    assert client.get('/api/law/status').json()['stats'] is None
    web.LAW_DB.parent.mkdir(parents=True)
    lawsync.lock_path(web.LAW_DB).write_text(json.dumps(dict(pid=1, done=5)), encoding='utf-8')
    assert client.post('/api/law/sync').status_code == 409


def test_index_is_not_cached(client):
    r = client.get('/')
    if r.status_code == 200:
        assert r.headers['cache-control'] == 'no-cache'
