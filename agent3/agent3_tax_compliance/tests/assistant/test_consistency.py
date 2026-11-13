"""Business regressions use synthetic temporary workspaces, never the running company."""
import dataclasses
import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.assistant import web, synth, pipeline
from src.assistant import decisions, accounting
from support import managed_company


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    monkeypatch.setattr(web, '_as_of', lambda ws: date(2026, 11, 11))
    c = TestClient(web.app)
    wid = managed_company(c, demo=True)
    base = f'/api/workspaces/{wid}'
    c.post(base + '/run').raise_for_status()
    return c, base, web.WORKSPACES / wid


def send(c, base, **body):
    report = c.get(base + '/report').json()
    journal = c.get(base + '/decisions')
    body = dict(request_id=__import__('uuid').uuid4().hex, report_revision=report['meta']['report_revision'], **body)
    return c.post(base + '/decisions', json=body, headers={'If-Match': journal.headers['etag']})


def test_not_claimed_is_excluded_and_scopes_keep_history(env):
    c, base, ws = env
    rep = c.get(base + '/report').json()
    inv = next(i for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i['duplicate_of'])
    key = inv['key']
    assert send(c, base, invoice_key=key, action='NOT_CLAIMED', evidence='Not claimed', by='A').status_code == 200
    assert send(c, base, invoice_key=key, action='PAYMENT_EVIDENCE_ATTACHED', evidence='Payment', by='B').status_code == 200
    current = decisions.effective(ws)
    assert current[key]['deduction']['action'] == 'NOT_CLAIMED'
    assert current[key]['payment']['by'] == 'B'
    assert len(decisions.history(ws)) >= 2
    v = c.get(base + '/vat-summary').json()
    assert sum(Decimal(r['not_claimed_vat']) for r in v['rows']) == Decimal(inv['vat'])


def test_direct_and_review_scenarios(env):
    c, base, ws = env
    rep = c.get(base + '/report').json()
    pack = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))
    v = accounting.vat_summary(rep, dict(pack['profile'], vat_method='DIRECT'))
    assert v['calculation_status'] == 'UNSUPPORTED_DIRECT'
    assert all(r['net'] is None and r['net_min'] is None and r['input_safe'] is None for r in v['rows'])
    v = accounting.vat_summary(rep, pack['profile'])
    for r in v['rows']:
        assert r['input_vat'] == r['not_claimed_vat'] + r['at_risk'] + r['review_vat'] + r['no_alert_vat']
        assert r['net_max'] - r['net_min'] == r['review_vat']


def test_portal_xlsx_is_used_and_invalid_replacement_preserves_active(env, tmp_path):
    c, base, ws = env
    from src.assistant.sources import read_table
    from src.assistant.portal_lists import active_path
    original = active_path(ws, __import__('src.assistant.pack', fromlist=['load_pack']).load_pack(ws / 'pack.json'))
    rows = read_table(original)
    x = tmp_path / 'list.xlsx'
    synth._write_xlsx(x, rows)
    r = c.put(base + '/inbox?name=list.xlsx', content=x.read_bytes())
    assert r.status_code == 200
    assert r.json()['files'][0]['kind'] == 'portal_list'
    rep = c.post(base + '/run').json()
    assert rep['meta']['counts']['portal_rows'] == len(rows) - 1
    manifest = (ws / 'portal/active.json').read_bytes()
    r = c.put(base + '/inbox?name=bad.csv', content=b'MST nguoi ban,invalid\nx,y')
    assert (ws / 'portal/active.json').read_bytes() == manifest


def test_decisions_require_preconditions_and_validate_ownership(env):
    c, base, ws = env
    assert c.post(base + '/decisions', json={}).status_code == 428
    r = send(c, base, invoice_key='missing', action='NOT_CLAIMED', evidence='x', by='A')
    assert r.status_code == 422
    assert not (ws / 'decisions_v2.json').exists()


def test_freshness_and_export_do_not_confuse_inputs(env, monkeypatch):
    c, base, ws = env
    assert not c.get(base + '/freshness').json()['stale']
    c.get(base + '/export/hoa-don.xlsx').raise_for_status()
    assert not c.get(base + '/freshness').json()['stale']
    monkeypatch.setattr(web, '_as_of', lambda ws: date(2026, 11, 12))
    assert c.get(base + '/freshness').json()['stale']


def test_r14_can_be_resolved_without_changing_tax(env):
    c, base, ws = env
    rep = c.get(base + '/report').json()
    item = next(i for i in rep['items'] if i['code'].startswith('R14'))
    before = rep['totals']['at_risk_vat']
    r = send(c, base, finding_id=item['finding_id'], action='CONFIRMED_NON_REVENUE',
             category='INTERNAL_TRANSFER', evidence='Internal bank transfer', by='A')
    assert r.status_code == 200, r.text
    after = c.get(base + '/report').json()
    assert next(i for i in after['items'] if i['finding_id'] == item['finding_id'])['status'] == 'INFO'
    assert after['totals']['at_risk_vat'] == before


def test_chart_matches_totals(env):
    c, base, _ = env
    rep = c.get(base + '/report').json()
    assert sum(Decimal(r['AT_RISK']) for r in rep['totals']['series']) == Decimal(rep['totals']['at_risk_vat'])
    assert sum(Decimal(r['REVIEW']) for r in rep['totals']['series']) == Decimal(rep['totals']['review_vat'])


def test_retry_after_report_failure_is_exactly_once_and_legacy_is_untouched(env, monkeypatch):
    c, base, ws = env
    legacy = (ws / 'decisions.json').read_bytes()
    rep = c.get(base + '/report').json()
    key = next(i['key'] for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i['duplicate_of'])
    body = dict(request_id='lost-response', report_revision=rep['meta']['report_revision'], invoice_key=key,
                action='NOT_CLAIMED', evidence='Temporary evidence', by='Reviewer')
    headers = {'If-Match': c.get(base + '/decisions').headers['etag']}
    old_write = web.report_mod.write
    monkeypatch.setattr(web.report_mod, 'write', lambda *a: (_ for _ in ()).throw(OSError('disk unavailable')))
    first = c.post(base + '/decisions', json=body, headers=headers)
    assert first.status_code == 200 and first.json()['saved'] and first.json()['report_pending']
    count = len(decisions.history(ws))
    monkeypatch.setattr(web.report_mod, 'write', old_write)
    retry = c.post(base + '/decisions', json=body, headers=headers)
    assert retry.status_code == 200 and not retry.json()['report_pending']
    assert len(decisions.history(ws)) == count
    assert (ws / 'decisions.json').read_bytes() == legacy
    assert not c.get(base + '/freshness').json()['stale']
    body['evidence'] = 'Different request using same id'
    assert c.post(base + '/decisions', json=body, headers=headers).status_code == 409


def test_bulk_validation_is_atomic_and_stale_versions_are_rejected(env):
    c, base, ws = env
    rep = c.get(base + '/report').json()
    key = next(i['key'] for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i['duplicate_of'])
    before = decisions.history(ws)
    r = send(c, base, invoice_keys=[key, 'unknown'], action='NOT_CLAIMED', evidence='x', by='A')
    assert r.status_code == 422 and decisions.history(ws) == before
    old = c.get(base + '/decisions').headers['etag']
    assert send(c, base, invoice_key=key, action='NOT_CLAIMED', evidence='x', by='A').status_code == 200
    body = dict(request_id='stale', report_revision=rep['meta']['report_revision'], invoice_key=key,
                action='PAYMENT_EVIDENCE_ATTACHED', evidence='x', by='A')
    assert c.post(base + '/decisions', json=body, headers={'If-Match': old}).status_code == 412
    assert c.post(base + '/decisions', json=body, headers={'If-Match': c.get(base + '/decisions').headers['etag']}).status_code == 409


def test_changed_invoice_does_not_inherit_confirmation(env):
    c, base, ws = env
    rep = c.get(base + '/report').json()
    inv = next(i for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i['duplicate_of'])
    assert send(c, base, invoice_key=inv['key'], action='NOT_CLAIMED', evidence='For original bytes', by='A').status_code == 200
    source = ws / 'invoices/purchase' / inv['file']
    source.write_bytes(source.read_bytes() + b'\n')
    after = c.post(base + '/run').json()
    assert inv['key'] not in after['meta']['not_claimed_keys']
    assert any(e.get('invoice_key') == inv['key'] for e in decisions.history(ws))


def test_bank_format_admin_and_optimistic_lock(env, monkeypatch):
    from src.assistant import admin
    c, base, ws = env
    fmt = dict(name='New format', columns=dict(date='Date', debit='Debit', description='Memo'))
    assert c.post(base + '/bank/formats', json=fmt).status_code == 428
    assert c.post(base + '/bank/formats', json=fmt, headers={'If-Match': '"old"'}).status_code == 412
    monkeypatch.setattr(admin, 'is_admin', lambda req: False)
    assert c.post(base + '/bank/formats', json=fmt, headers={'If-Match': c.get(base + '/pack').headers['etag']}).status_code == 401


def test_legacy_conflicting_lists_require_selection(env, tmp_path):
    from src.assistant.portal_lists import active_path
    from src.assistant.pack import load_pack
    c, base, ws = env
    pack = load_pack(ws / 'pack.json')
    path = active_path(ws, pack)
    other = path.with_name('different.csv')
    text = path.read_text(encoding='utf-8-sig')
    other.write_text(text.replace('1650000', '1650001'), encoding='utf-8')
    # Ensure the second file differs even if this particular fixture has different amounts.
    other.write_text(other.read_text(encoding='utf-8') + text.splitlines()[-1] + '\n', encoding='utf-8')
    with pytest.raises(ValueError):
        active_path(ws, pack)
    assert c.put(base + '/portal/active-list', json={'name': path.name}).status_code == 200
    assert c.post(base + '/run').status_code == 200


def test_preview_reads_without_changing_workspace(env):
    c, base, ws = env
    path = next((ws / 'invoices/purchase').glob('*.xml'))
    before = pipeline.input_digest(ws)
    response = c.post(base + '/inbox/preview?name=preview.xml', content=path.read_bytes())
    assert response.status_code == 200 and response.json()['ready']
    assert pipeline.input_digest(ws) == before
    assert not (ws / 'invoices/purchase/preview.xml').exists()


def test_quarterly_exposure_uses_calendar_and_unknown_filing(env):
    c, base, ws = env
    master = json.loads(web.bridge.source.read_text(encoding='utf-8'))
    master['filing_period'] = 'QUARTER'
    web.bridge.source.write_text(json.dumps(master), encoding='utf-8')
    ctx = c.post('/api/platform/sync', headers={'X-Agent3-Platform-Token': web.bridge.token}).json()
    c.headers['X-Agent3-Profile-Revision'] = ctx['profile_revision']
    rep = c.post(base + '/run').json()
    due = next(r['due'] for r in rep['calendar'] if r['obligation'] == 'VAT')
    ex = c.get(base + '/exposure').json()
    assert ex and all(r['due'] == due and r['declared'] is None and r['overdue'] for r in ex.values())


def test_missing_vat_is_not_zero_and_signed_scenarios_remain_exact(env):
    c, base, ws = env
    rep = c.get(base + '/report').json()
    inv = next(i for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i['duplicate_of'])
    inv['vat'] = None
    profile = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))['profile']
    rows = accounting.vat_summary(rep, profile)['rows']
    row = next(r for r in rows if r['period_key'] == inv['issue_date'][:7])
    assert row['input_vat'] is None and row['net_min'] is None and row['calculation_status'] == 'INCOMPLETE'


def test_concurrent_decisions_have_one_winner(env):
    from concurrent.futures import ThreadPoolExecutor
    c, base, ws = env
    rep = c.get(base + '/report').json()
    key = next(i['key'] for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i['duplicate_of'])
    headers = dict(c.headers)
    headers['If-Match'] = c.get(base + '/decisions').headers['etag']
    initial = len(decisions.history(ws))
    def save(n):
        with TestClient(web.app) as other:
            return other.post(base + '/decisions', headers=headers, json=dict(request_id=f'concurrent-{n}',
                report_revision=rep['meta']['report_revision'], invoice_key=key, action='NOT_CLAIMED', evidence='Concurrent check', by=str(n))).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, [1, 2]))
    assert sorted(results) == [200, 412]
    assert len(decisions.history(ws)) == initial + 1


def test_portal_agent3_check_calls_real_non_mutating_preview(env):
    from test_portal_bridge import isolated_function
    from urllib.parse import quote
    c, base, ws = env
    before = pipeline.input_digest(ws)
    def transport(method, url, body, headers=None, timeout=None):
        result = c.request(method, url, content=body, headers=headers)
        return result.status_code, result.json()
    check = isolated_function('check', dict(company=lambda: {}, health=lambda aid: True,
        agent3_workspace=lambda: ws.name, ensure_agent3_workspace=lambda: dict(state='ok', id=ws.name,
        profile_revision=c.headers['X-Agent3-Profile-Revision']), call=transport,
        agent_url=lambda aid, path: path, quote=quote))
    source = next((ws / 'invoices/purchase').glob('*.xml'))
    assert check('agent3', {'name':'preview.xml'}, source.read_bytes())['state'] == 'ready'
    assert check('agent3', {'name':'invalid.xml'}, b'<HDon/>')['state'] == 'error'
    assert pipeline.input_digest(ws) == before
