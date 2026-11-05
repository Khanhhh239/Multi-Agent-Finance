"""Enterprise adaptation: the fixed core reads each enterprise's own configuration."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.assistant import ai, pipeline, web


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    monkeypatch.setattr(web, '_as_of', lambda ws: date(2026, 10, 15))
    c = TestClient(web.app)
    demo = c.post('/api/demo').json()['id']
    return c, demo


def test_fiscal_year_and_own_days_off_change_the_calendar(env):
    c, demo = env
    ws = web.WORKSPACES / demo
    pack = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))
    pack['profile']['fiscal_year_end_month'] = 6
    pack['days_off'] = ['2026-10-20']
    assert c.put(f'/api/workspaces/{demo}/pack?by=Kế toán trưởng', json=pack).status_code == 200
    rep = pipeline.run(ws, pipeline.DEFAULT_RULESET, date(2026, 10, 15))
    cal = {e['period']: e for e in rep.calendar}
    fin = next(e for p, e in cal.items() if p.startswith('Quyết toán'))
    assert fin['period'] == 'Quyết toán thuế TNDN năm tài chính kết thúc 30/06/2027' and fin['due'] == date(2027, 9, 30)
    sep = cal['Tờ khai thuế GTGT tháng 09/2026']
    assert sep['due'] == date(2026, 10, 21) and sep['moved_from'] == date(2026, 10, 20)          # the enterprise's own day off
    hist = c.get(f'/api/workspaces/{demo}/pack/history').json()
    assert hist[0]['by'] == 'Kế toán trưởng' and 'hồ sơ' in hist[0]['changed'] and 'ngày nghỉ' in hist[0]['changed']


def test_new_enterprise_can_copy_configuration_but_keeps_its_own_profile(env):
    c, demo = env
    r = c.post('/api/workspaces', json=dict(profile=dict(tax_code='0100109106', legal_name='Công ty TNHH Nhà hàng Thử', vat_method='DEDUCTION', filing_period='QUARTER'),
                                             copy_from=demo, ai_categories=[dict(name='Nguyên liệu thực phẩm', description='thịt, cá, rau dùng chế biến món ăn')]))
    assert r.status_code == 200
    new = c.get(f'/api/workspaces/{r.json()["id"]}/pack').json()
    src = c.get(f'/api/workspaces/{demo}/pack').json()
    assert new['bank_formats'] == src['bank_formats'] and new['policies'] == src['policies']
    assert new['profile']['legal_name'] == 'Công ty TNHH Nhà hàng Thử' and new['ai_categories'][0]['name'] == 'Nguyên liệu thực phẩm'
    bad = c.post('/api/workspaces', json=dict(profile=dict(tax_code='0101243150', legal_name='X', fiscal_year_end_month=13)))
    assert bad.status_code == 422


def test_enterprise_categories_reach_the_model_and_count_as_business(tmp_path):
    seen = {}

    class LLM:
        def chat(self, system, user, schema=None, num_predict=900):
            seen['system'], seen['enum'] = system, schema['properties']['lines']['items']['properties']['category']['enum']
            return json.dumps(dict(lines=[dict(index=0, category=[e for e in seen['enum'] if e.startswith('RIENG_')][0], business_use='CO',
                                               reason='Thịt bò dùng chế biến món ăn')])), {}
    out = ai.classify_lines(ai.AI(LLM(), tmp_path / 'c.sqlite3'), dict(seller_name='Chợ đầu mối', descriptions=['Thịt bò Úc']),
                            ['5610 Nhà hàng'], (('Nguyên liệu thực phẩm', 'thịt, cá, rau dùng chế biến món ăn'),))
    assert 'Nguyên liệu thực phẩm' in seen['system'] or 'thịt, cá, rau' in seen['system']
    assert out['labels'][0]['verified'] and not ai.flagged(out['labels'])
