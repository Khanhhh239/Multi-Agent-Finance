from support import managed_company, pack_headers
"""One drop zone: mixed files are put where they belong; file status, mapping preview and coverage warnings."""
import io
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.assistant import synth, web


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    monkeypatch.setattr(web, '_as_of', lambda ws: __import__('datetime').date(2026, 10, 15))
    demo = tmp_path / 'demo'
    synth.generate(demo, seed=7)
    c = TestClient(web.app)
    pack = (demo / 'pack.json').read_text(encoding='utf-8')
    import json
    prof = json.loads(pack)['profile']
    wid = managed_company(c, profile=prof)
    return c, wid, demo


def test_mixed_drop_is_sorted_by_content(env):
    c, wid, demo = env
    global TAX
    TAX = c.get(f'/api/workspaces/{wid}/pack').json()['profile']['tax_code']
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for p in list((demo / 'invoices' / 'purchase').glob('*.xml'))[:10]:
            z.write(p, f'lan_lon/{p.name}')
        for k in range(3):
            z.writestr(f'ban_ra_{k}.xml', f'<HDon><DLHDon><NDHDon><NBan><MST>{TAX}</MST></NBan><NMua><MST>0100109106</MST></NMua></NDHDon></DLHDon></HDon>')
        for p in (demo / 'bank').glob('*'):
            z.write(p, p.name)
        for p in (demo / 'portal').glob('*'):
            z.write(p, p.name)
        z.writestr('ghi_chu.txt', 'không phải sao kê')
        z.writestr('cty_khac.xml', '<HDon><DLHDon><NDHDon><NBan><MST>0100109106</MST></NBan><NMua><MST>0101243150</MST></NMua></NDHDon></DLHDon></HDon>')
    files = c.put(f'/api/workspaces/{wid}/inbox?name=tat_ca.zip', content=buf.getvalue()).json()['files']
    kinds = {}
    for f in files:
        kinds.setdefault(f['kind'], []).append(f['file'])
    assert len(kinds['purchase_xml']) == 10 and len(kinds['sales_xml']) == 3
    assert len(kinds['bank']) == 2 and len(kinds['portal_list']) == 1
    rejected = {f['file']: f['reason'] for f in files if f['kind'] is None}
    assert set(rejected) == {'ghi_chu.txt', 'cty_khac.xml'} and 'không có mã số thuế' in rejected['cty_khac.xml']


def test_file_status_mapping_preview_and_coverage(env):
    c, wid, demo = env
    for p in sorted((demo / 'invoices' / 'purchase').glob('*.xml')):
        c.put(f'/api/workspaces/{wid}/inbox?name={p.name}', content=p.read_bytes())
    bank_a = next((demo / 'bank').glob('*.csv'))
    c.put(f'/api/workspaces/{wid}/files/bank?name={bank_a.name}', content=bank_a.read_bytes())   # direct upload: no automatic layout recognition
    det = c.get(f'/api/workspaces/{wid}/details/purchase_xml').json()
    assert len(det) == 47 and all(d['date'] for d in det if d['ok'])
    bank = c.get(f'/api/workspaces/{wid}/details/bank').json()
    assert bank[0]['ok'] is False and 'Nhận dạng cột' in bank[0]['errors'][0]          # no saved format yet
    s = c.post(f'/api/workspaces/{wid}/bank/suggest?name={bank_a.name}').json()
    assert s['format']['columns']['debit'] in s['headers']
    wrong = dict(s['format'], columns=dict(s['format']['columns'], debit=s['format']['columns']['credit']))
    pv = c.post(f'/api/workspaces/{wid}/bank/preview?name={bank_a.name}', json=wrong).json()
    assert pv['preview'] and all(not r.get('debit') or r.get('error') for r in pv['preview'][:3])  # user sees the effect at once
    warn = c.get(f'/api/workspaces/{wid}/coverage').json()
    assert any('sao kê chưa đọc được' in w['title'] for w in warn)
    c.post(f'/api/workspaces/{wid}/bank/formats', json=s['format'], headers={'If-Match': c.get(f'/api/workspaces/{wid}/pack').headers['etag']}).raise_for_status()
    assert c.get(f'/api/workspaces/{wid}/details/bank').json()[0]['ok'] is True
    titles = [w['title'] for w in c.get(f'/api/workspaces/{wid}/coverage').json()]
    assert not any('chưa đọc được' in t for t in titles) and any('bảng kê' in t for t in titles)


def test_the_same_bank_statement_dropped_twice_is_kept_once(tmp_path):
    from src.assistant.inbox import ingest
    from src.assistant.pack import load_pack
    from src.assistant import synth
    ws = tmp_path / 'ws'
    synth.generate(ws, seed=3)
    pack = load_pack(ws / 'pack.json')
    raw = next((ws / 'bank').glob('*.csv')).read_bytes()
    before = len(list((ws / 'bank').glob('*')))
    first = ingest(ws, 'sao_ke_moi.csv', raw, pack.tax_code, pack)
    second = ingest(ws, 'sao_ke_moi_lan_2.csv', raw, pack.tax_code, pack)
    assert first[0]['kind'] == 'bank'
    assert second[0].get('duplicate') and 'đã nạp trước đó' in second[0]['reason']
    assert len(list((ws / 'bank').glob('*'))) == before        # the demo already holds this very file, so nothing new was stored


def test_dropping_the_same_invoice_file_twice_changes_nothing_but_a_renamed_copy_is_kept_for_the_duplicate_rule(tmp_path):
    from src.assistant.inbox import ingest
    from src.assistant.pack import load_pack
    from src.assistant import synth
    ws = tmp_path / 'ws'
    synth.generate(ws, seed=3)
    pack = load_pack(ws / 'pack.json')
    src = sorted((ws / 'invoices' / 'purchase').glob('*.xml'))[0]
    raw = src.read_bytes()
    count = len(list((ws / 'invoices' / 'purchase').glob('*.xml')))
    again = ingest(ws, src.name, raw, pack.tax_code, pack)
    assert again[0].get('duplicate') and len(list((ws / 'invoices' / 'purchase').glob('*.xml'))) == count
    ingest(ws, 'ban_sao_khac_ten.xml', raw, pack.tax_code, pack)
    assert len(list((ws / 'invoices' / 'purchase').glob('*.xml'))) == count + 1
