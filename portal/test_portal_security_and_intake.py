"""Comprehensive security, route-auth, Agent 4 multi-turn proxy, Vietnamese bank VND money(),
and Agent 2 canonical 1.1.0 intake regression tests for Sổ Son Portal.
"""
from __future__ import annotations

import concurrent.futures
import csv
import io
import json
import math
import os
import sys
import tempfile
import threading
import time
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest

from portal import agent2_intake, bank_intake, server

ROOT = Path(__file__).resolve().parent.parent


def _base_face(seed: float = 0.08) -> list[float]:
    return [round(seed + 0.002 * ((i * 7) % 13), 6) for i in range(128)]


def _http_call(port: int, method: str, path: str, body: dict | bytes | None = None, headers: dict | None = None):
    url = f'http://127.0.0.1:{port}{path}'
    hdrs = dict(headers or {})
    if isinstance(body, dict):
        raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
        hdrs.setdefault('Content-Type', 'application/json')
    elif isinstance(body, bytes):
        raw = body
    else:
        raw = None
    req = Request(url, data=raw, method=method, headers=hdrs)
    try:
        with urlopen(req, timeout=10) as resp:
            payload = resp.read()
            return resp.status, json.loads(payload.decode('utf-8')) if payload else {}
    except HTTPError as exc:
        payload = exc.read()
        try:
            parsed = json.loads(payload.decode('utf-8'))
        except ValueError:
            parsed = {'raw': payload.decode('utf-8', 'replace')}
        return exc.code, parsed


@pytest.fixture()
def isolated_portal(tmp_path: Path):
    work = tmp_path / 'workspace'
    pending = work / 'pending'
    logs = work / 'logs'
    pending.mkdir(parents=True)
    logs.mkdir(parents=True)
    sec_file = work / 'intake_security.json'
    audit_file = work / 'audit.jsonl'
    batch_file = work / 'batches.json'
    company_file = work / 'company.json'

    with patch.multiple(
        server,
        WORK=work,
        PENDING=pending,
        LOGS=logs,
        SECURITY_FILE=sec_file,
        AUDIT_FILE=audit_file,
        BATCH_FILE=batch_file,
        COMPANY_FILE=company_file,
        SESSIONS={},
        BIOMETRIC_CHALLENGES={},
        FAILS={'n': 0, 'until': 0.0},
    ):
        yield work


@pytest.fixture()
def live_portal(isolated_portal: Path):
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    port = httpd.server_port
    origin = f'http://127.0.0.1:{port}'
    origins = (origin, f'http://localhost:{port}')
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    with patch.multiple(server, ORIGIN=origin, ORIGINS=origins):
        thread.start()
        try:
            yield port, isolated_portal
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


class TestFaceIDSecurity:
    def test_nan_and_inf_descriptors_never_bypass_face_verify(self, isolated_portal: Path):
        server.set_password('AdminSecret123!', 'AdminSecret123!')
        enrolled = _base_face(0.10)
        server.save_face_descriptor(enrolled)
        server.SESSIONS.clear()
        server._sync_sessions_to_disk()

        malicious_vectors = [
            [float('nan')] + enrolled[1:],
            enrolled[:64] + [float('nan')] + enrolled[65:],
            [float('inf')] + enrolled[1:],
            [float('-inf')] + enrolled[1:],
            ['nan'] + enrolled[1:],
            ['Infinity'] + enrolled[1:],
            ['-Infinity'] + enrolled[1:],
            [None] + enrolled[1:],
            [True] + enrolled[1:],
            [False] * 128,
            [0.0] * 128,
            [1e-9] * 128,
            [1e5] * 128,
            enrolled[:127],
            enrolled + [0.1],
        ]
        for bad in malicious_vectors:
            with pytest.raises(ValueError):
                server.verify_face_descriptor(bad)
            with pytest.raises(ValueError):
                server.save_face_descriptor(bad)
        assert server.SESSIONS == {}

    def test_http_face_verify_rejects_raw_json_nan_and_preserves_lockout_counter(self, live_portal):
        port, _ = live_portal
        server.set_password('AdminSecret123!', 'AdminSecret123!')
        enrolled = _base_face(0.12)
        server.save_face_descriptor(enrolled)
        server.SESSIONS.clear()
        server._sync_sessions_to_disk()
        server.FAILS.update(n=3, until=0.0)

        # Raw non-standard JSON literal NaN (parsed by Python json.loads into float('nan'))
        nan_json = ('{"descriptor": [NaN,' + ','.join('0.1' for _ in range(127)) + ']}').encode('utf-8')
        status, body = _http_call(
            port,
            'POST',
            '/api/intake/face/verify',
            nan_json,
            {'Content-Type': 'application/json', 'X-Platform': '1'},
        )
        assert status == 400
        assert 'token' not in body
        # Must NOT reset failed attempt counter on malformed/NaN probe!
        assert server.FAILS['n'] == 3

        # String "nan" injection as described in security audit
        status2, body2 = _http_call(
            port,
            'POST',
            '/api/intake/face/verify',
            {'descriptor': ['nan'] + [0.1] * 127},
            {'X-Platform': '1'},
        )
        assert status2 == 400
        assert 'token' not in body2
        assert server.FAILS['n'] == 3

    def test_invalid_threshold_and_tampered_enrolled_nan_rejected(self, isolated_portal: Path):
        server.set_password('AdminSecret123!', 'AdminSecret123!')
        enrolled = _base_face(0.10)
        server.save_face_descriptor(enrolled)

        for bad_thresh in (float('nan'), float('inf'), 0.0, -0.1, 1.5, True):
            with pytest.raises(ValueError):
                server.verify_face_descriptor(enrolled, threshold=bad_thresh)

        # Simulate disk tampering injecting NaN into stored descriptor
        sec = server.read_json(server.SECURITY_FILE, {})
        sec['ai_face_descriptor'][0] = 'nan'
        server.write_json(server.SECURITY_FILE, sec)
        with pytest.raises(ValueError):
            server.verify_face_descriptor(enrolled)

    def test_multiframe_averaging_and_interframe_jump_rejection(self, live_portal):
        port, _ = live_portal
        st, setup_res = _http_call(
            port,
            'POST',
            '/api/intake/setup',
            {'password': 'AdminSecret123!', 'confirm': 'AdminSecret123!'},
            {'X-Platform': '1'},
        )
        assert st == 200
        admin_token = setup_res['token']

        base = _base_face(0.15)
        frame1 = [v - 0.004 for v in base]
        frame2 = list(base)
        frame3 = [v + 0.004 for v in base]

        # Enroll with 3 consistent frames
        st, reg_res = _http_call(
            port,
            'POST',
            '/api/intake/face/register',
            {'descriptors': [frame1, frame2, frame3]},
            {'X-Platform': '1', 'X-Session': admin_token},
        )
        assert st == 200
        assert reg_res['ok'] is True
        saved = server.read_json(server.SECURITY_FILE, {})['ai_face_descriptor']
        assert saved == pytest.approx(base, abs=1e-7)
        assert server.read_json(server.SECURITY_FILE, {})['ai_face_frames'] == 3

        # Verify with 2 consistent frames
        probe1 = [v + 0.002 for v in base]
        probe2 = [v - 0.001 for v in base]
        st, ver_res = _http_call(
            port,
            'POST',
            '/api/intake/face/verify',
            {'descriptors': [probe1, probe2]},
            {'X-Platform': '1'},
        )
        assert st == 200
        assert server.session_left(ver_res['token'], touch=False) > 0

        # Wild frame jump (frame 2 belongs to a different person / swapped photo) must fail
        wild_frame = [-v for v in base]
        st_jump, _ = _http_call(
            port,
            'POST',
            '/api/intake/face/verify',
            {'descriptors': [probe1, wild_frame]},
            {'X-Platform': '1'},
        )
        assert st_jump == 400

        # NaN hidden in 2nd frame of multi-frame array must fail
        nan_second = list(probe1)
        nan_second[127] = float('nan')
        with pytest.raises(ValueError):
            server.verify_face_descriptor(descriptors=[probe1, nan_second])


class TestRouteAuthAndAtomicWrite:
    def test_profile_details_require_the_shared_unlock_session(self, live_portal):
        port, _ = live_portal
        profile = dict(server.COMPANY_FIELDS, code='MPX10', legal_name='Minh Phat',
                       tax_code='0999999905', registered_address='Private address', industry='Private industry')
        server.write_json(server.COMPANY_FILE, profile)
        token = server.set_password('AdminSecret123!', 'AdminSecret123!')
        with patch.object(server, 'agent_state', return_value={'id': 'agent1', 'state': 'stopped'}):
            status, locked = _http_call(port, 'GET', '/api/state')
            assert status == 200
            assert locked['company']['legal_name'] == profile['legal_name']
            for key in ('tax_code', 'registered_address', 'industry', 'vat_method', 'date_format'):
                assert locked['company'][key] == ''
            status, opened = _http_call(port, 'GET', '/api/state', headers={'X-Session': token})
            assert status == 200 and opened['company']['tax_code'] == profile['tax_code']
            assert opened['company']['registered_address'] == profile['registered_address']
            assert _http_call(port, 'PUT', '/api/company', profile, {'X-Platform': '1'})[0] == 401
            server.lock_session(token)
            assert _http_call(port, 'GET', '/api/state', headers={'X-Session': token})[1]['company']['tax_code'] == ''

    def test_demo_mode_without_enrollment_vs_strict_auth_when_faceid_enrolled(self, live_portal):
        port, _ = live_portal
        with patch.object(server, 'agent1_key', return_value='secret-agent1-bearer'), \
             patch.object(server, 'start_agent', side_effect=lambda aid: {'id': aid, 'state': 'running'}), \
             patch.object(server, 'stop_agent', side_effect=lambda aid: {'id': aid, 'state': 'stopped'}), \
             patch.object(server, 'restart_agent', side_effect=lambda aid: {'id': aid, 'state': 'running', 'restarted': True}):

            # 1. With 0 FaceID users enrolled: seamless demo usability on local/same-origin
            st, res = _http_call(port, 'GET', '/api/agents/agent1/key', headers={'X-Platform': '1'})
            assert st == 200
            assert res['key'] == 'secret-agent1-bearer'

            # Cross-origin browser fetch to /api/agents/agent1/key is STILL blocked even in demo mode
            st_cors, _ = _http_call(port, 'GET', '/api/agents/agent1/key', headers={'Origin': 'https://attacker.example'})
            assert st_cors == 403

            st_start, _ = _http_call(port, 'POST', '/api/agents/agent1/start', {}, {'X-Platform': '1'})
            assert st_start == 200

            # 2. Enroll FaceID user -> sensitive routes immediately enforce session authentication
            server.set_password('AdminSecret123!', 'AdminSecret123!')
            enrolled = _base_face(0.11)
            server.save_face_descriptor(enrolled)
            server.SESSIONS.clear()
            server._sync_sessions_to_disk()
            assert server.has_biometric() is True

            # Unauthenticated secret & control routes return 401
            assert _http_call(port, 'GET', '/api/agents/agent1/key')[0] == 401
            assert _http_call(port, 'GET', '/api/agents/agent1/log')[0] == 401
            assert _http_call(port, 'POST', '/api/agents/agent1/start', {}, {'X-Platform': '1'})[0] == 401
            assert _http_call(port, 'POST', '/api/agents/agent1/stop', {}, {'X-Platform': '1'})[0] == 401
            assert _http_call(port, 'POST', '/api/agents/agent1/restart', {}, {'X-Platform': '1'})[0] == 401
            assert _http_call(port, 'PUT', '/api/company', {'code': 'A', 'legal_name': 'B'}, {'X-Platform': '1'})[0] == 401
            assert _http_call(port, 'GET', '/api/auth/users')[0] == 401
            assert _http_call(port, 'POST', '/api/auth/users', {'name': 'Evil', 'descriptor': enrolled}, {'X-Platform': '1'})[0] == 401
            assert _http_call(port, 'POST', '/api/inbox?name=a.csv', b'a,b\n1,2\n', {'X-Platform': '1'})[0] == 401

            # Authenticate via FaceID and verify authorized access works (X-Session, Bearer, Cookie)
            st_ver, ver_body = _http_call(port, 'POST', '/api/intake/face/verify', {'descriptor': enrolled}, {'X-Platform': '1'})
            assert st_ver == 200
            tok = ver_body['token']

            st_key, key_body = _http_call(port, 'GET', '/api/agents/agent1/key', headers={'X-Session': tok})
            assert st_key == 200 and key_body['key'] == 'secret-agent1-bearer'

            st_restart, restart_body = _http_call(
                port, 'POST', '/api/agents/agent1/restart', {}, {'X-Platform': '1', 'Authorization': f'Bearer {tok}'}
            )
            assert st_restart == 200 and restart_body['restarted'] is True

            st_users, users_body = _http_call(port, 'GET', '/api/auth/users', headers={'Cookie': f'kt_session={tok}'})
            assert st_users == 200
            assert users_body['enrolled'] is True
            assert len(users_body['users']) == 1
            assert 'descriptor' not in users_body['users'][0]

            # Add and remove a named FaceID user via /api/auth/users
            second_face = _base_face(0.22)
            st_add, add_body = _http_call(
                port,
                'POST',
                '/api/auth/users',
                {'name': 'Kế toán trưởng', 'role': 'chief_accountant', 'descriptors': [second_face, second_face]},
                {'X-Platform': '1', 'X-Session': tok},
            )
            assert st_add == 200
            uid = add_body['user']['id']
            assert 'descriptor' not in add_body['user']

            st_del, _ = _http_call(port, 'DELETE', f'/api/auth/users/{uid}', headers={'X-Platform': '1', 'X-Session': tok})
            assert st_del == 200

    def test_atomic_write_json_under_concurrent_load_leaves_no_tmp_or_corruption(self, tmp_path: Path):
        target = tmp_path / 'concurrent_state.json'
        observed_tmps: list[str] = []
        orig_replace = os.replace

        def spy_replace(src, dst):
            observed_tmps.append(Path(src).name)
            return orig_replace(src, dst)

        with patch('portal.server.os.replace', side_effect=spy_replace):
            server.write_json(target, {'init': True})

        assert len(observed_tmps) == 1
        assert observed_tmps[0].startswith(f'concurrent_state.json.{os.getpid()}.')
        assert observed_tmps[0].endswith('.tmp')

        def worker(idx: int):
            for step in range(20):
                server.write_json(target, {'worker': idx, 'step': step, 'items': list(range(25))})
                loaded = server.read_json(target, None)
                assert isinstance(loaded, dict) and 'worker' in loaded

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(worker, i) for i in range(12)]
            for fut in futures:
                fut.result(timeout=15)

        final_doc = json.loads(target.read_text(encoding='utf-8'))
        assert 'worker' in final_doc
        assert list(tmp_path.glob('*.tmp')) == []


class TestAgent4ProxyAndLaunch:
    def test_agent4_query_forwards_session_id_choice_and_context(self, live_portal):
        port, _ = live_portal
        captured_calls = []

        def fake_call(method, url, body=None, headers=None, timeout=60):
            captured_calls.append((method, url, body, headers))
            return 200, {
                'api_version': 'v1',
                'request_id': 'req-1',
                'status': 'ready',
                'error': None,
                'answer': 'Lợi nhuận gộp quý 3/2026 là 1.250.000.000 VND.',
                'data': None,
                'interpretation': None,
                'provenance': None,
                'warnings': [],
            }

        sid = '0123456789abcdef0123456789abcdef'
        with patch.object(server, 'call', side_effect=fake_call):
            st, res = _http_call(
                port,
                'POST',
                '/api/agent4/query',
                {
                    'question': 'Lợi nhuận gộp',
                    'session_id': sid,
                    'selected_choice_id': 'gross_profit',
                    'context': {'as_of_date': '2026-10-14'},
                },
                {'X-Platform': '1'},
            )

        assert st == 200
        assert res['status'] == 'ready'
        assert len(captured_calls) == 1
        method, url, forwarded, headers = captured_calls[0]
        assert method == 'POST'
        assert url.endswith('/v1/query')
        assert forwarded['session_id'] == sid
        assert forwarded['selected_choice_id'] == 'gross_profit'
        assert forwarded['context'] == {'as_of_date': '2026-10-14'}
        assert forwarded['question'] == 'Lợi nhuận gộp'

    def test_agent4_query_choice_only_and_strict_intake_fallback(self, live_portal):
        port, _ = live_portal
        calls = []
        sid = 'abcdef0123456789abcdef0123456789'

        def strict_agent4_call(method, url, body=None, headers=None, timeout=60):
            calls.append(body)
            if 'selected_choice_id' in body or 'context' in body:
                return 400, {
                    'api_version': 'v1',
                    'request_id': 'r1',
                    'status': 'error',
                    'error': {'code': 'invalid_request', 'stage': 'query_intake', 'message': 'Unexpected fields.'},
                    'answer': '',
                    'warnings': [],
                }
            return 200, {
                'api_version': 'v1',
                'request_id': 'r2',
                'status': 'ready',
                'error': None,
                'answer': 'Đã chọn chỉ tiêu gross_profit.',
                'data': None,
                'interpretation': None,
                'provenance': None,
                'warnings': [],
            }

        with patch.object(server, 'call', side_effect=strict_agent4_call):
            st, res = _http_call(
                port,
                'POST',
                '/api/agent4/query',
                {'session_id': sid, 'selected_choice_id': 'gross_profit', 'context': {'branch': 'HN'}},
                {'X-Platform': '1'},
            )
        assert st == 200
        assert res['status'] == 'ready'
        assert len(calls) == 2
        assert calls[0]['selected_choice_id'] == 'gross_profit'
        assert set(calls[1].keys()) == {'api_version', 'question', 'locale', 'session_id', 'options'}
        assert calls[1]['session_id'] == sid
        assert calls[1]['question'] == 'gross_profit'

    def test_launch_spec_agent4_sets_both_selection_config_env_vars(self, isolated_portal: Path):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AGENT4_SELECTION_CONFIG', None)
            os.environ.pop('AGENT4_METRIC_SELECTION_CONFIG', None)
            _, _, env = server.launch_spec('agent4')
            assert env['AGENT4_SELECTION_CONFIG'] == 'config/eval_governed_lexical.yaml'
            assert env['AGENT4_METRIC_SELECTION_CONFIG'] == 'config/eval_governed_lexical.yaml'

        with patch.dict(os.environ, {'AGENT4_METRIC_SELECTION_CONFIG': 'config/custom_local.yaml'}, clear=False):
            os.environ.pop('AGENT4_SELECTION_CONFIG', None)
            _, _, env_override = server.launch_spec('agent4')
            assert env_override['AGENT4_SELECTION_CONFIG'] == 'config/custom_local.yaml'
            assert env_override['AGENT4_METRIC_SELECTION_CONFIG'] == 'config/custom_local.yaml'


class TestVietnameseBankMoney:
    @pytest.mark.parametrize(
        'raw,expected',
        [
            ('500,000', 500_000),
            ('15,000', 15_000),
            ('1,250,000', 1_250_000),
            ('12,500,000', 12_500_000),
            ('500.000', 500_000),
            ('12.500.000', 12_500_000),
            ('1.250.000,00', 1_250_000),
            ('12.500.000,00', 12_500_000),
            ('500,000.00', 500_000),
            ('12,500,000.00', 12_500_000),
            ('-666,387,909', -666_387_909),
            ('-500,000', -500_000),
            ('(500,000)', -500_000),
            ('(12.500.000)', -12_500_000),
            ('(500,000 VND)', -500_000),
            ('(500,000) VND', -500_000),
            ('500,000 VND', 500_000),
            ('500.000 đ', 500_000),
            ('12,500,000 ₫', 12_500_000),
            ('VND 1,250,000', 1_250_000),
            ('+2,500,000', 2_500_000),
            ('500000', 500_000),
            ('500000.00', 500_000),
            ('500000,00', 500_000),
            ('0', 0),
            ('0.00', 0),
            ('0,00', 0),
            ('', 0),
            ('   ', 0),
            (Decimal('12500000.00'), 12_500_000),
            (500_000, 500_000),
        ],
    )
    def test_vnd_money_exact_parsing_across_formats(self, raw, expected):
        for fmt in ('vi-VN', 'plain'):
            parsed = bank_intake.money(raw, fmt)
            assert isinstance(parsed, Decimal)
            assert parsed == Decimal(expected), f'{raw!r} under {fmt} parsed as {parsed}, expected {expected}'

    @pytest.mark.parametrize(
        'invalid',
        [
            '500,000.50',
            '1.250.000,25',
            '500.50',
            '500,50',
            '0,500',
            '0.500',
            '12,34,567',
            '12.34.567',
            '--500,000',
            '-(500,000)',
            '(-500,000)',
            '500,000 USD',
            'NaN',
            'Infinity',
            True,
            False,
            None,
            Decimal('9007199254740992'),
        ],
    )
    def test_vnd_money_rejects_fractional_and_malformed_values(self, invalid):
        with pytest.raises(ValueError):
            bank_intake.money(invalid, 'vi-VN')

    def test_five_vietnamese_banks_csv_statements_normalize_without_1000x_loss(self):
        cases = [
            # Vietcombank: comma thousands + .00 cents, negative debit
            (
                'VCB',
                'Số tham chiếu,Số tài khoản,Ngày giao dịch,Số tiền ghi nợ,Số tiền ghi có,Nội dung giao dịch\n'
                'VCB001,0071000123456,14/10/2026,,"12,500,000.00",Khach hang thanh toan HD01\n'
                'VCB002,0071000123456,15/10/2026,"-500,000.00",,Phi dich vu kho bai\n',
                [('VCB001', 'in', '12500000'), ('VCB002', 'out', '500000')],
            ),
            # Techcombank: comma thousands + accounting parentheses for debit
            (
                'TCB',
                'Mã giao dịch,Tài khoản,Ngày hạch toán,Ghi Nợ,Ghi Có,Diễn giải\n'
                'TCB001,19034567890011,2026-10-14,,"1,250,000",Thu tien ban hang\n'
                'TCB002,19034567890011,2026-10-15,"(500,000)",,Thanh toan dien nuoc\n',
                [('TCB001', 'in', '1250000'), ('TCB002', 'out', '500000')],
            ),
            # ACB: dot thousands + ,00 decimal suffix
            (
                'ACB',
                'Mã giao dịch;Số tài khoản;Ngày giao dịch;Phát sinh nợ;Phát sinh có;Nội dung\n'
                'ACB001;88886666;14/10/2026;;12.500.000,00;Thu cong no\n'
                'ACB002;88886666;15/10/2026;500.000;;Chi van phong pham\n',
                [('ACB001', 'in', '12500000'), ('ACB002', 'out', '500000')],
            ),
            # MB Bank: direction + amount with VND suffix
            (
                'MB',
                'Mã giao dịch,Số tài khoản,Ngày giao dịch,Thu chi,Số tiền,Nội dung\n'
                'MB001,0987654321,14/10/2026,Thu,"500,000 VND",Thu le\n'
                'MB002,0987654321,15/10/2026,Chi,"-15,000 VND",Phi chuyen khoan\n',
                [('MB001', 'in', '500000'), ('MB002', 'out', '15000')],
            ),
            # BIDV: dot thousands + đ currency suffix
            (
                'BIDV',
                'Số giao dịch;Số tài khoản;Ngày hiệu lực;Tiền ra;Tiền vào;Chi tiết giao dịch\n'
                'BIDV01;31410009999999;14/10/2026;;1.250.000,00;Thu tien HD99\n'
                'BIDV02;31410009999999;15/10/2026;500.000 đ;;Tra NCC\n',
                [('BIDV01', 'in', '1250000'), ('BIDV02', 'out', '500000')],
            ),
        ]
        for bank_name, csv_text, expected in cases:
            raw = csv_text.encode('utf-8')
            record = dict(
                server.classify(f'{bank_name}.csv', raw),
                name=f'{bank_name}.csv',
                intake_context=dict(code='MPX10', agent2_company='MPX10', tax_code='0999999905', date_format='dmy', number_format='vi-VN'),
            )
            assert record['kind'] == 'shared_bank', bank_name
            rows = server.shared_bank_rows(record, raw)
            actual = [(r[0], r[3], r[4]) for r in rows]
            assert actual == expected, f'{bank_name} mismatch: {actual} != {expected}'

            a1_csv = list(csv.DictReader(io.StringIO(bank_intake.project(rows, 'agent1', date_format='dmy', number_format='vi-VN').decode('utf-8'))))
            a3_csv = list(csv.DictReader(io.StringIO(bank_intake.project(rows, 'agent3').decode('utf-8'))))
            assert len(a1_csv) == 2 and len(a3_csv) == 2


class TestAgent2IntakeSmoothness:
    def test_agent2_contract_conversion_handles_formatted_vnd_and_validates_schema(self):
        csv_text = (
            'transaction_id,posted_at,created_at,approved_at,txn_type,amount_vnd,payment_channel,vendor_id,employee_id,creator_id,business_purpose\n'
            'TX001,2026-10-14,2026-10-14 08:15:00,2026-10-14 09:00:00,vendor_payment,"12,500,000.00",bank,V000001,,E000001,Thanh toan lo hang\n'
            'TX002,15/10/2026,,,customer_receipt,"500,000 VND",bank,,,E000001,Thu tien khach\n'
            'TX003,2026-10-16T10:30:00+07:00,,,payroll,"(1.250.000,00)",bank,,E000005,E000001,Chi luong\n'
            'TX004,2026-10-16T11:00:00+07:00,,,sales_invoice,"9,999,000",journal,,,E000001,But toan doanh thu\n'
        )
        body, summary = agent2_intake.build_contract(
            csv_text.encode('utf-8'),
            tenant='demo',
            company='MPX10',
            company_name='Công ty Minh Phát',
            name='01_transactions.csv',
        )
        assert summary['rows'] == 3
        assert summary['skipped'] == 1
        doc = json.loads(body.decode('utf-8'))
        assert doc['contract_version'] == '1.1.0'
        amounts = {tx['record_id']: tx['amount_vnd'] for tx in doc['transactions']}
        assert amounts == {'TX001': 12_500_000, 'TX002': 500_000, 'TX003': 1_250_000}
        assert agent2_intake.Decimal_or_int('-666,387,909') == -666_387_909

        # Verify canonical 1.1.0 required tables, integer VND types, and RFC3339 timestamps
        required_tables = {
            'companies', 'transactions', 'vendors', 'invoices', 'payment_allocations',
            'employees', 'approvals', 'supporting_documents',
        }
        assert required_tables <= set(doc.keys())
        for tx in doc['transactions']:
            assert type(tx['amount_vnd']) is int
            assert agent2_intake._ISO_TZ_RE.fullmatch(tx['effective_at'])
            assert agent2_intake._ISO_TZ_RE.fullmatch(tx['observed_at'])

        # Also run shared finance_input 1.1.0 validator when jsonschema is available
        shared_src = ROOT / 'shared' / 'finance_input' / 'src'
        if shared_src.is_dir():
            with patch.object(sys, 'path', [str(shared_src), *sys.path]):
                try:
                    from finance_input import AccessScope, check_core
                except ModuleNotFoundError:
                    check_core = None
                if check_core is not None:
                    scope = AccessScope(
                        tenant_id='demo',
                        company_ids=frozenset({'MPX10'}),
                        actor_id='portal-operator',
                        permissions=frozenset({'data.import'}),
                    )
                    assert check_core(doc, scope) == []

    def test_agent2_large_csv_streaming_completes_quickly(self):
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator='\n')
        writer.writerow([
            'transaction_id', 'posted_at', 'created_at', 'approved_at', 'txn_type',
            'amount_vnd', 'payment_channel', 'vendor_id', 'employee_id', 'creator_id', 'business_purpose',
        ])
        for i in range(20_000):
            is_bank = (i % 2 == 0)
            writer.writerow([
                f'J{i:06d}',
                '2026-10-14T10:00:00+07:00',
                '2026-10-14T09:00:00+07:00',
                '2026-10-14T09:30:00+07:00',
                'vendor_payment' if is_bank else 'sales_invoice',
                '500,000' if is_bank else '1,000,000',
                'bank' if is_bank else 'journal',
                f'V{i % 50:06d}' if is_bank else '',
                '',
                'E000001',
                'Thanh toán chuyển khoản định kỳ',
            ])
        raw = buf.getvalue().encode('utf-8')
        t0 = time.perf_counter()
        body, summary = agent2_intake.build_contract(raw, 'demo', 'MPX10', 'Minh Phát', name='large.csv')
        elapsed = time.perf_counter() - t0
        assert summary['rows'] == 10_000
        assert summary['skipped'] == 10_000
        assert len(body) < agent2_intake.MAX_BYTES
        assert elapsed < 3.0, f'Large CSV conversion took too long: {elapsed:.2f}s'
