"""Provision synthetic, temporary fixtures through the trusted portal bridge."""
import json

from src.assistant import synth, web
from src.assistant.platform_context import Bridge


def managed_company(client, profile=None, demo=False):
    root = web.WORKSPACES
    source = root.parent / 'test-company.json'
    if demo:
        ws = root / 'legacy-company'
        synth.generate(ws)
        pack = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))
        # This fixture represents an existing enterprise layout; HTTP demo creation is forbidden.
        pack.pop('simulated', None)
        (ws / 'pack.json').write_text(json.dumps(pack), encoding='utf-8')
        profile = pack['profile']
    profile = profile or dict(tax_code='0109999982', legal_name='Doanh nghiệp kiểm thử', vat_method='DEDUCTION', filing_period='MONTH', fiscal_year_end_month=12)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(dict(profile, code='TEST')), encoding='utf-8')
    web.bridge = Bridge(str(source), 'test-backend-secret', 'http://127.0.0.1:8800', root, web._bridge_save)
    response = client.post('/api/platform/sync', headers={'X-Agent3-Platform-Token': web.bridge.token})
    assert response.status_code == 200, response.text
    c = response.json()
    client.headers['X-Agent3-Profile-Revision'] = c['profile_revision']
    return c['workspace_id']


def pack_headers(client, wid):
    return {'If-Match': client.get(f'/api/workspaces/{wid}/pack').headers['etag']}


def decide(client, wid, body, bulk=False):
    import uuid
    base = f'/api/workspaces/{wid}'
    report = client.get(base + '/report').json()
    headers = {'If-Match': client.get(base + '/decisions').headers['etag']}
    payload = dict(body, request_id=uuid.uuid4().hex, report_revision=report['meta']['report_revision'])
    return client.post(base + '/decisions' + ('/bulk' if bulk else ''), json=payload, headers=headers)
