"""Exercise only Agent 3 integration functions, without importing the live portal config."""
import ast
import hashlib
import importlib.util
import json
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from src.assistant import web
from src.assistant.pack import load_pack
from src.assistant.sources import read_bank_statement
from support import managed_company


def isolated_function(name, env):
    path = Path(__file__).resolve().parents[4] / 'portal' / 'server.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), env)
    return env[name]


def test_launch_passes_trusted_bridge_environment_after_custom_config(tmp_path):
    demo = {'code': 'MPX10', 'tax_code': '0999999905'}
    env = dict(os=os, json=json, CFG={'demo_company': demo}, company=lambda: {}, agent_root=lambda aid: tmp_path, agent_port=lambda aid: 8640,
               agent_python=lambda aid: 'python', agent_cfg=lambda aid: {'env': {'AGENT3_PLATFORM_TOKEN': 'untrusted override',
                                                                                 'AGENT3_DEMO_COMPANY': '{}'}},
               path_of=lambda value, default: value, COMPANY_FILE=tmp_path / 'company.json', ORIGIN='http://127.0.0.1:8800', AGENT3_TOKEN='backend secret')
    args, cwd, child_env = isolated_function('launch_spec', env)('agent3')
    assert args == ['python', '-m', 'src.assistant.web']
    assert child_env['AGENT3_PLATFORM_TOKEN'] == 'backend secret'
    assert child_env['AGENT3_COMPANY_PROFILE_FILE'] == str(tmp_path / 'company.json')
    assert child_env['AGENT3_PORTAL_URL'] == 'http://127.0.0.1:8800'
    assert json.loads(child_env['AGENT3_DEMO_COMPANY']) == demo


@pytest.mark.parametrize('status,expected', [(200, 'ok'), (0, 'offline'), (403, 'error'), (404, 'error')])
def test_portal_sync_never_uses_browser_password_or_leaks_token(status, expected):
    calls = []
    def call(*args):
        calls.append(args)
        return status, dict(workspace_id='0109999982', profile_revision='revision', detail='backend secret')
    env = dict(call=call, agent_url=lambda aid, path: path, AGENT3_TOKEN='backend secret')
    result = isolated_function('ensure_agent3_workspace', env)('old browser password')
    assert result['state'] == expected
    assert calls == [('POST', '/api/platform/sync', {}, {'X-Agent3-Platform-Token': 'backend secret'})]
    assert 'backend secret' not in str(result)
    assert 'old browser password' not in str(result)


@pytest.mark.parametrize('failure', ['offline', 'lost_response', 'stale_revision'])
def test_shared_bank_commit_retries_with_real_managed_agent3(tmp_path, monkeypatch, failure):
    """Exercise portal commit -> token sync -> guarded inbox; all state is temporary."""
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'agent3')
    client = TestClient(web.app)
    wid = managed_company(client)
    bridge = web.bridge
    client.headers.pop('X-Agent3-Profile-Revision')  # The portal must supply this header itself.
    module_path = Path(__file__).resolve().parents[4] / 'portal' / 'bank_intake.py'
    spec = importlib.util.spec_from_file_location('isolated_bank_intake', module_path)
    bank_intake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bank_intake)
    rows = [('TEST-001', '000012345678', '2026-10-01', 'in', '12000000', '2026-10-01', 'sales', 'Thu tiền', '000011112222', 'Đối tác'),
            ('TEST-002', '000012345678', '2026-10-02', 'out', '8500000', '2026-10-02', 'suppliers', 'Thanh toán', '000033334444', 'Nhà cung cấp')]
    pending = tmp_path / 'pending'
    pending.mkdir()
    raw = b'original bank export'
    (pending / 'test.bin').write_bytes(raw)
    context = dict(code='TEST', tax_code='0109999982', number_format='plain', date_format='iso')
    record = dict(id='test', name='bank.csv', kind='shared_bank', label='Sao kê dùng chung', size=len(raw),
                  intake_context=context, targets=['agent1', 'agent3'], checks={aid: {'state': 'ready'} for aid in ('agent1', 'agent3')})
    batches, removed, calls = [], [], []
    uploads = 0
    def call(method, url, body=None, headers=None, timeout=120):
        nonlocal uploads
        calls.append((method, url))
        if url.startswith('/agent1/'):
            return 200, {'accepted': len(rows)}
        assert url.startswith('/agent3/')
        path = url.removeprefix('/agent3')
        if method == 'PUT':
            uploads += 1
            assert body == bank_intake.project(rows, 'agent3')
            assert headers.get('X-Agent3-Profile-Revision')
            assert 'sao_ke_' + hashlib.sha256(body).hexdigest()[:16] + '.csv' in path
            if uploads == 1 and failure == 'offline':
                return 503, {'error': 'Mock offline'}
            if uploads == 1 and failure == 'stale_revision':
                master = json.loads(bridge.source.read_text(encoding='utf-8'))
                master['legal_name'] = 'Tên mới khi đang gửi'
                bridge.source.write_text(json.dumps(master), encoding='utf-8')
        response = client.request(method, path, json=body if isinstance(body, dict) else None,
                                  content=body if isinstance(body, bytes) else None, headers=headers)
        if method == 'PUT' and uploads == 1 and failure == 'lost_response':
            assert response.status_code == 200
            return 503, {'error': 'Mock response lost after write'}
        result = response.json()
        return response.status_code, result if response.is_success else {'error': result.get('detail')}
    def write_json(path, data):
        if path == tmp_path / 'batches.json':
            batches[:] = data
        else:
            path.write_text(json.dumps(data), encoding='utf-8')
    env = dict(hashlib=hashlib, uuid=uuid, time=time, quote=quote, LOCK=threading.RLock(),
               WORK=tmp_path, PENDING=pending, BATCH_FILE=tmp_path / 'batches.json', bank_intake=bank_intake,
               intake_context=lambda: dict(context), pending_file=lambda fid, ctx: record,
               current_batches=lambda: list(batches), batches=lambda: list(batches),
               shared_bank_rows=lambda rec, content: rows, check=lambda *args, **kwargs: {'state': 'ready', 'preview': 'test'},
               agent1_key=lambda: 'mock-key', call=call, agent_url=lambda aid, path: '/' + aid + path,
               write_json=write_json, audit=lambda *args: None, remove_file=removed.append, pending=lambda: [],
               AGENT3_TOKEN=bridge.token)
    isolated_function('ensure_agent3_workspace', env)
    commit = isolated_function('commit', env)
    first = commit(['test'])
    assert first['files'][0]['results']['agent3']['state'] == 'error'
    assert record['applied']['agent1']['state'] == 'done'
    record['checks']['agent3'] = {'state': 'ready'}  # The user rechecks the failed target before retrying.
    second = commit(['test'], 'Thử lại sau lỗi gửi Agent 3')
    assert second['files'][0]['results']['agent3']['state'] == 'done'
    assert len([url for method, url in calls if url.startswith('/agent1/')]) == 1
    assert removed == ['test']
    ws = web.WORKSPACES / wid
    files = list((ws / 'bank').glob('*.csv'))
    assert len(files) == 1
    pack = load_pack(ws / 'pack.json')
    txns = read_bank_statement(files[0], pack)
    assert [(str(txn.amount), txn.direction) for txn in txns] == [('12000000', 'IN'), ('8500000', 'OUT')]
    assert txns[0].counterparty_account == '000011112222'
    assert json.loads((ws / 'pack.json').read_text(encoding='utf-8'))['bank_formats'] == []
    assert len([p for p in (tmp_path / 'bank_sources').rglob('*') if p.is_file()]) == 1


def test_commit_never_sends_to_agent3_if_portal_company_changes_during_sync(tmp_path):
    before = {'code': 'COMPANY-A', 'tax_code': '0109999982'}
    after = {'code': 'COMPANY-B', 'tax_code': '0100109106'}
    contexts = iter([before, after])
    record = dict(id='test', name='bank.csv', kind='statement_or_list', intake_context=before,
                  targets=['agent3'], checks={'agent3': {'state': 'ready'}})
    (tmp_path / 'test.bin').write_bytes(b'bank export from A')
    env = dict(PENDING=tmp_path, intake_context=lambda: next(contexts),
               pending_file=lambda fid, context: record, current_batches=lambda: [],
               ensure_agent3_workspace=lambda: {'state': 'ok', 'id': after['tax_code'], 'profile_revision': 'new-revision'},
               call=lambda *args, **kwargs: pytest.fail('Must not send company A data to company B'))
    with pytest.raises(ValueError, match='Không tệp nào được ghi'):
        isolated_function('commit', env)(['test'])
