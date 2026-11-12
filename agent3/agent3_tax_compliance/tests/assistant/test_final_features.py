from support import managed_company, pack_headers, decide
"""R14, exposure, declared figures, bulk and confirmed-OK decisions, Excel export, deadline open items."""
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.assistant import web


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    monkeypatch.setattr(web, '_as_of', lambda ws: date(2026, 10, 15))
    c = TestClient(web.app)
    wid = managed_company(c, demo=True)
    rep = c.post(f'/api/workspaces/{wid}/run').json()
    return c, wid, rep


def test_receipt_without_sales_invoice_and_deadline_open_items(env):
    c, wid, rep = env
    r14 = [i for i in rep['items'] if i['code'] == 'R14_RECEIPT_WITHOUT_SALES_INVOICE']
    assert len(r14) == 1 and '26/09/2026' in r14[0]['detail'] and '120.000.000' in r14[0]['detail']   # S21 only; July and August have invoices
    sep = next(x for x in rep['calendar'] if x['period'] == 'Tờ khai thuế GTGT tháng 09/2026')
    assert sep['open_items'] > 0


def test_exposure_compares_self_correction_with_being_found(env):
    c, wid, rep = env
    ex = c.get(f'/api/workspaces/{wid}/exposure').json()
    i = next(n for n, it in enumerate(rep['items']) if it['status'] == 'AT_RISK' and it['code'] == 'R01_PAYMENT_EVIDENCE')
    e = ex[str(i)]
    assert e['declared'] is None and e['overdue'] is True and e['days_late'] > 0
    assert float(e['penalty']) == round(float(e['amount']) * 0.2) and float(e['interest']) == round(float(e['amount']) * 0.0003 * e['days_late'])
    assert e['scenario'] and e['filing_status'] == 'UNKNOWN'


def test_declared_figures_show_the_difference(env):
    c, wid, rep = env
    assert c.put(f'/api/workspaces/{wid}/declared', json={'Tháng 07/2026': {'output_vat': '20.000.000', 'input_vat': '15.084.000'}}).status_code == 200
    rows = {r['period']: r for r in c.get(f'/api/workspaces/{wid}/vat-summary').json()['rows']}
    jul = rows['Tháng 07/2026']
    assert float(jul['diff_output']) == 20000000 - float(jul['output_vat'])
    assert float(jul['diff_input']) == 15084000 - float(jul['input_safe'])


def test_bulk_and_confirmed_ok_decisions(env):
    c, wid, rep = env
    review = [i for i in rep['items'] if i['status'] == 'REVIEW' and i['code'] in ('R08_RISKY_SELLER', 'R13_LOW_VOLUME_SELLER')]
    keys = [i['invoice_keys'][0] for i in review]
    out = decide(c, wid, dict(finding_ids=[i['finding_id'] for i in review], action='CONFIRMED_OK', evidence='Đã kiểm tra hợp đồng và giao nhận', by='Kế toán trưởng'), bulk=True).json()
    assert out['decisions'] == len(keys)
    after = c.get(f'/api/workspaces/{wid}/report').json()
    done = [i for i in after['items'] if i['invoice_keys'] and i['invoice_keys'][0] in keys and i['code'] in ('R08_RISKY_SELLER', 'R13_LOW_VOLUME_SELLER')]
    assert done and all(i['status'] == 'INFO' and 'Kế toán trưởng' in i['detail'] for i in done)
    bad = decide(c, wid, dict(invoice_keys=keys, action='IGNORE', evidence='x', by='y'), bulk=True)
    assert bad.status_code == 422


def test_excel_exports_open(env):
    c, wid, rep = env
    for kind in ('viec-can-xu-ly', 'hoa-don', 'quyet-dinh'):
        r = c.get(f'/api/workspaces/{wid}/export/{kind}.xlsx')
        assert r.status_code == 200
        z = zipfile.ZipFile(__import__('io').BytesIO(r.content))
        assert 'xl/worksheets/sheet1.xml' in z.namelist()
