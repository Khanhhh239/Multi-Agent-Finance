"""Managed enterprise boundaries. All files and writes live under pytest's temporary root."""
import concurrent.futures
import contextvars
import json
import threading

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.assistant import web, web_ai
from src.assistant.platform_context import Bridge, REVISION
from support import managed_company, pack_headers


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    c = TestClient(web.app)
    wid = managed_company(c)
    return c, wid, web.bridge


def write_master(bridge, **changes):
    data = json.loads(bridge.source.read_text(encoding='utf-8'))
    data.update(changes)
    bridge.source.write_text(json.dumps(data), encoding='utf-8')


def sync(c, bridge):
    r = c.post('/api/platform/sync', headers={'X-Agent3-Platform-Token': bridge.token})
    if r.status_code == 200:
        c.headers['X-Agent3-Profile-Revision'] = r.json()['profile_revision']
    return r


def test_sync_is_backend_only_and_idempotent(env):
    c, wid, b = env
    assert c.post('/api/platform/sync', json={'profile': {'legal_name': 'injected'}}).status_code == 403
    assert c.post('/api/platform/sync', headers={'X-Agent3-Platform-Token': 'wrong'}).status_code == 403
    history = c.get(f'/api/workspaces/{wid}/pack/history').json()
    for _ in range(3):
        assert sync(c, b).status_code == 200
    assert c.get(f'/api/workspaces/{wid}/pack/history').json() == history
    public = c.get('/api/platform/context').text + c.get('/api/workspaces').text
    assert b.token not in public
    assert c.post('/api/workspaces', json={}).status_code == 410
    assert c.post('/api/demo').status_code == 410


def test_shared_profile_readonly_and_optimistic_lock(env):
    c, wid, b = env
    url = f'/api/workspaces/{wid}/pack'
    pack = c.get(url).json()
    headers = pack_headers(c, wid)
    assert c.put(url, json=pack).status_code == 428
    tampered = dict(pack, profile=dict(pack['profile'], legal_name='forged'))
    assert c.put(url, json=tampered, headers=headers).status_code == 422
    pack['days_off'] = ['2027-02-05']
    assert c.put(url, json=pack, headers=headers).status_code == 200
    assert c.put(url, json=pack, headers=headers).status_code == 412
    write_master(b, legal_name='Tên mới từ portal', fiscal_year_end_month=6)
    assert c.get(url).status_code == 409
    assert sync(c, b).status_code == 200
    after = c.get(url).json()
    assert after['profile']['legal_name'] == 'Tên mới từ portal'
    assert after['days_off'] == ['2027-02-05']


def test_other_company_and_stale_revision_are_blocked(env):
    c, wid, b = env
    old_revision = c.headers['X-Agent3-Profile-Revision']
    old_file = b.root / wid / 'decisions.json'
    old_file.write_text('[]', encoding='utf-8')
    write_master(b, tax_code='0100109106', legal_name='Doanh nghiệp B')
    assert c.get(f'/api/workspaces/{wid}/pack').status_code == 409
    result = sync(c, b).json()
    assert result['workspace_id'] != wid
    assert c.get(f'/api/workspaces/{wid}/pack').status_code == 403
    url = f'/api/workspaces/{result["workspace_id"]}/pack'
    assert c.get(url, headers={'X-Agent3-Profile-Revision': old_revision}).status_code == 409
    assert old_file.read_text(encoding='utf-8') == '[]'
    assert [w['id'] for w in c.get('/api/workspaces').json()] == [result['workspace_id']]


@pytest.mark.parametrize('failure', ['missing', 'invalid', 'empty', 'array'])
def test_bad_master_never_falls_back_to_old_company(env, failure):
    c, wid, b = env
    if failure == 'missing':
        b.source.unlink()
    elif failure == 'invalid':
        write_master(b, tax_code='0109999981')
    elif failure == 'array':
        b.source.write_text('[]', encoding='utf-8')
    else:
        write_master(b, legal_name='')
    assert c.get('/api/workspaces').json() == []
    assert c.get(f'/api/workspaces/{wid}/pack').status_code == 409
    assert sync(c, b).status_code == 409


def test_duplicate_or_simulated_workspace_is_not_automatically_adopted(env):
    c, wid, b = env
    folder = b.root / 'other'
    folder.mkdir()
    pack = c.get(f'/api/workspaces/{wid}/pack').json()
    (folder / 'pack.json').write_text(json.dumps(pack), encoding='utf-8')
    assert c.get('/api/platform/context').json()['state'] == 'conflict'
    assert sync(c, b).status_code == 409
    pack['simulated'] = True
    (folder / 'pack.json').write_text(json.dumps(pack), encoding='utf-8')
    assert sync(c, b).status_code == 409


def test_concurrent_saves_only_one_wins(env):
    c, wid, b = env
    url = f'/api/workspaces/{wid}/pack'
    pack = c.get(url).json()
    headers = dict(c.headers, **pack_headers(c, wid))
    def save(day):
        with TestClient(web.app) as other:
            return other.put(url, json=dict(pack, days_off=[day]), headers=headers).status_code
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, ['2027-02-05', '2027-02-08']))
    assert sorted(results) == [200, 412]
    assert len(json.loads((b.root / wid / 'pack_history.json').read_text(encoding='utf-8'))) == 2


def test_background_result_cannot_publish_after_master_change(env):
    c, wid, b = env
    token = REVISION.set(c.headers['X-Agent3-Profile-Revision'])
    context = contextvars.copy_context()
    REVISION.reset(token)
    write_master(b, legal_name='Changed during model request')
    path = b.root / wid / 'ai' / 'bank_links.json'
    with pytest.raises(HTTPException):
        context.run(web_ai._write, path, [])
    assert not path.exists()


def test_unconnected_mode_exposes_no_workspaces(env):
    c, wid, b = env
    web.bridge = Bridge(None, '', '', b.root, web._bridge_save)
    assert c.get('/api/platform/context').json()['state'] == 'unconnected'
    assert c.get('/api/workspaces').json() == []
    assert c.get(f'/api/workspaces/{wid}/pack').status_code == 409


def test_unknown_folder_is_not_silently_claimed(env):
    c, wid, b = env
    folder = b.root / '0100109106'
    folder.mkdir()
    evidence = folder / 'decisions.json'
    evidence.write_text('[]', encoding='utf-8')
    write_master(b, tax_code='0100109106', legal_name='Doanh nghiệp B')
    assert sync(c, b).status_code == 409
    assert not (folder / 'pack.json').exists()
    assert evidence.read_text(encoding='utf-8') == '[]'


def test_actual_background_job_rejects_late_result(env):
    c, wid, b = env
    started, finish, done = threading.Event(), threading.Event(), threading.Event()
    path = b.root / wid / 'ai' / 'test-result.json'
    def work(job):
        started.set()
        assert finish.wait(5)
        try:
            web_ai._write(path, {'late': True})
        finally:
            done.set()
    token = REVISION.set(c.headers['X-Agent3-Profile-Revision'])
    try:
        job = web_ai._start(wid, 'isolated test', work)
    finally:
        REVISION.reset(token)
    try:
        assert started.wait(5)
        assert c.get(f'/api/workspaces/{wid}/ai').json()['job']['running'] is True
        write_master(b, legal_name='Changed while job running')
    finally:
        finish.set()
    assert done.wait(5)
    assert not path.exists()
