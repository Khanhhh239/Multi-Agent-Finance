from support import managed_company, pack_headers
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
    demo = managed_company(c, demo=True)
    return c, demo


def test_fiscal_year_and_own_days_off_change_the_calendar(env):
    c, demo = env
    ws = web.WORKSPACES / demo
    pack = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))
    source = web.bridge.source
    master = json.loads(source.read_text(encoding='utf-8'))
    master['fiscal_year_end_month'] = 6
    source.write_text(json.dumps(master), encoding='utf-8')
    context = c.post('/api/platform/sync', headers={'X-Agent3-Platform-Token': web.bridge.token}).json()
    c.headers['X-Agent3-Profile-Revision'] = context['profile_revision']
    pack = c.get(f'/api/workspaces/{demo}/pack').json()
    pack['days_off'] = ['2026-10-20']
    assert c.put(f'/api/workspaces/{demo}/pack?by=Kế toán trưởng', json=pack, headers=pack_headers(c, demo)).status_code == 200
    rep = pipeline.run(ws, pipeline.DEFAULT_RULESET, date(2026, 10, 15))
    cal = {e['period']: e for e in rep.calendar}
    fin = next(e for p, e in cal.items() if p.startswith('Quyết toán'))
    assert fin['period'] == 'Quyết toán thuế TNDN năm tài chính kết thúc 30/06/2027' and fin['due'] == date(2027, 9, 30)
    sep = cal['Tờ khai thuế GTGT tháng 09/2026']
    assert sep['due'] == date(2026, 10, 21) and sep['moved_from'] == date(2026, 10, 20)          # the enterprise's own day off
    hist = c.get(f'/api/workspaces/{demo}/pack/history').json()
    assert hist[0]['by'] == 'Kế toán trưởng' and 'ngày nghỉ' in hist[0]['changed']


def test_new_enterprise_can_only_be_created_from_portal(env):
    c, demo = env
    assert c.post('/api/workspaces', json=dict(copy_from=demo)).status_code == 410



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
