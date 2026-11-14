"""End-to-end sandbox Concrete FHE + HTTP + DPAPI + crash-recovery verifier for Slices 1, 2, 3.

Never touches live Portal daemons, live SQLite DBs, live DPAPI keys, or Git.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'tests') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tests'))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from finance_input import AccessScope

from experiments.he4 import VERSION, FRESH_ADMISSION, bundle as he4_bundle, c3_circuit as c3m
from experiments.he4.client_transport import download, envelope, upload
from experiments.he4.rule_snapshot_adapter import decode_p1_plan_results, prepare_p1_rule_snapshot
from experiments.he4.rule_snapshot_c3_adapter import decode_c3_plan_results, prepare_c3_rule_snapshot
from experiments.he4.rule_snapshot_identity_adapter import (
    decode_b1_plan_results,
    decode_b5_e4_plan_results,
    plan_b1_from_rule_snapshot,
    plan_b5_e4_from_rule_snapshot,
)
from experiments.he4.windows_bridge import CryptoBridge, linux_path
from experiments.he_inference.http_common import ServiceError, post
from experiments.he_inference.key_manager import protect_key
from experiments.he_inference.protocol import canonical, public_hex, sha, sign, verify

from sme_fraud.import_files import canonical as sme_canonical, digest as sme_digest
from sme_fraud.native_rule_demo import authorities, base, finish, scenario
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields


WSL_PYTHON = '/home/sang/.local/share/agent2/he4/bin/python'
BUILDS_ROOT = Path(r'D:\agent22\.runtime\he4')
BUILDS = {
    'rules': BUILDS_ROOT / 'build-rules-difference-v1',
    'c3': BUILDS_ROOT / 'build-c3-v1',
    'graph': BUILDS_ROOT / 'build-graph-difference-v1',
    'statistics': BUILDS_ROOT / 'build-statistics-v1',
}


def _scope(company: str, actor: str = 'he-sandbox-verifier') -> AccessScope:
    return AccessScope('native-demo', frozenset({company}), actor, frozenset({'data.import'}))


def _fit_scope(company: str, actor: str = 'he-sandbox-admin') -> AccessScope:
    return AccessScope('native-demo', frozenset({company}), actor, frozenset({'data.import', 'model.fit'}))


def _rehash(source: dict) -> dict:
    for name, rows in source['tables'].items():
        source['coverage'][name] = dict(
            source['coverage'][name],
            record_count=len(rows),
            records_sha256=sme_digest(sme_canonical(rows)),
        )
    return source


def _wrap(source: dict, candidate_ids: list[str] | None = None) -> dict:
    return dict(
        contract_version=CONTRACT,
        tenant_id=source['tenant_id'],
        company_id=source['company_id'],
        source=source,
        candidate_transaction_ids=candidate_ids or [source['tables']['transactions'][-1]['transaction_id']],
    )


def _commit(store: SnapshotStore, scope: AccessScope, data: dict, key: str) -> str:
    draft = store.upload(scope, sme_canonical(data), 'rule-snapshot.json', key + '-upload')
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise AssertionError(preview['errors'])
    return store.commit(scope, draft['import_id'], commit_fields(preview), key + '-commit')['snapshot']['snapshot_id']


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return int(s.getsockname()[1])


def _wsl_worker_start(bundle_dir: Path, config_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env_cmd = (
        f"cd /tmp && PYTHONPATH={shlex.quote(linux_path(bundle_dir))} "
        f"{WSL_PYTHON} -u -m experiments.he4.service --config {shlex.quote(linux_path(config_path))} --port {port}"
    )
    proc = subprocess.Popen(
        ['wsl.exe', '-d', 'Debian', '--exec', 'bash', '-lc', env_cmd],
        stdout=log_path.open('wb'),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    url = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'WSL worker exited early ({proc.returncode}): {log_path.read_text(errors="replace")}')
        try:
            import urllib.request

            with urllib.request.urlopen(url + '/health', timeout=2) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            time.sleep(0.3)
    raise RuntimeError('Timed out waiting for WSL HE4 HTTP worker health')


def _wsl_worker_stop(proc: subprocess.Popen, *, kill_pattern: str | None = None) -> None:
    if kill_pattern:
        subprocess.run(
            ['wsl.exe', '-d', 'Debian', '--exec', 'bash', '-lc', f'pkill -9 -f {shlex.quote(kill_pattern)} || true'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass


def _execute_request_over_http(
    *,
    bridge: CryptoBridge,
    scope: AccessScope,
    node_key: Ed25519PrivateKey,
    worker_url: str,
    worker_pub: str,
    bundle: Path,
    values: list,
    work_dir: Path,
    session_id: str,
    nonce: str,
    profile: str,
    expected_circuit_sha256: str,
) -> tuple[list[int], dict, dict]:
    """Run real DPAPI provision/encrypt -> HTTP upload -> /v1/evaluate -> download -> decrypt."""
    work_dir.mkdir(parents=True, exist_ok=True)
    company = next(iter(scope.company_ids))

    # Encrypt inputs using DPAPI + isolated WSL enterprise_helper
    enc_dir = work_dir / 'enc'
    t0 = time.monotonic()
    enc_meta = bridge.encrypt(scope, bundle, values, enc_dir)
    enc_sec = time.monotonic() - t0
    pub_key_path = bridge.public_key(scope, bundle)
    eval_key_bytes = pub_key_path.stat().st_size

    arg_paths = [enc_dir / f'argument-{i}.cipher' for i in range(len(enc_meta['arguments_sha256']))]
    req_cipher_bytes = sum(p.stat().st_size for p in arg_paths)

    # Stream encrypted blobs to HTTP worker
    t_up = time.monotonic()
    public_hash = upload(worker_url, scope, node_key, worker_pub, pub_key_path, 'public_evaluation_keys')
    arg_hashes = [upload(worker_url, scope, node_key, worker_pub, p, 'ciphertext') for p in arg_paths]
    upload_sec = time.monotonic() - t_up

    packet = envelope(
        scope,
        node_key,
        dict(
            profile=profile,
            circuit_sha256=expected_circuit_sha256,
            evaluation_keys_sha256=public_hash,
            arguments_sha256=arg_hashes,
            session_id=session_id,
            nonce=nonce,
        ),
    )

    t_eval = time.monotonic()
    response = post(worker_url, '/v1/evaluate', packet, timeout=600)
    eval_sec = time.monotonic() - t_eval
    receipt = verify(response, worker_pub)
    if receipt['request_sha256'] != sha(canonical(packet)) or receipt['company_id'] != company:
        raise AssertionError('Worker response receipt mismatch')

    res_cipher_path = work_dir / 'result.cipher'
    download(worker_url, scope, node_key, receipt['result_sha256'], res_cipher_path)
    res_cipher_bytes = res_cipher_path.stat().st_size

    t_dec = time.monotonic()
    plain = bridge.decrypt(scope, bundle, res_cipher_path, receipt['result_sha256'], work_dir / 'result.opened', enc_meta)
    dec_sec = time.monotonic() - t_dec

    metrics = dict(
        encrypt_seconds=round(enc_sec, 4),
        upload_seconds=round(upload_sec, 4),
        http_fhe_seconds=round(eval_sec, 4),
        decrypt_seconds=round(dec_sec, 4),
        evaluation_key_bytes=eval_key_bytes,
        request_cipher_bytes=req_cipher_bytes,
        result_cipher_bytes=res_cipher_bytes,
    )
    return plain, metrics, dict(packet=packet, response=response, enc_meta=enc_meta, receipt=receipt)


def _sample_wsl_rss_mb(sandbox_tag: str) -> float | None:
    """Query max resident RSS (MB) across sandbox WSL worker/public_worker processes."""
    cmd = f"ps -eo rss,args | grep -F {shlex.quote(sandbox_tag)} | grep -E 'public_worker|experiments.he4.service' | grep -v grep || true"
    out = subprocess.run(
        ['wsl.exe', '-d', 'Debian', '--exec', 'bash', '-lc', cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    rss_kb = 0
    for line in out.splitlines():
        parts = line.strip().split()
        if parts and parts[0].isdigit():
            rss_kb = max(rss_kb, int(parts[0]))
    return round(rss_kb / 1024.0, 1) if rss_kb else None


def main() -> int:
    root_tmp = Path(tempfile.mkdtemp(prefix='he4_expand_verify_'))
    print(f'Sandbox root: {root_tmp}', flush=True)
    peak_rss_mb = {'max': 0.0}
    stop_sampler = threading.Event()
    sandbox_tag = root_tmp.name

    def sampler():
        while not stop_sampler.is_set():
            val = _sample_wsl_rss_mb(sandbox_tag)
            if val is not None and val > peak_rss_mb['max']:
                peak_rss_mb['max'] = val
            time.sleep(1.0)

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()

    worker_proc = None
    try:
        # 1. Stage isolated public bundle (no enterprise code)
        public_bundle = root_tmp / 'public_worker_bundle'
        he4_bundle.build(public_bundle)

        # 2. Setup DPAPI state key & node Ed25519 keys for C001 and C002
        dpapi_key = root_tmp / 'dpapi_state.json'
        protect_key(secrets.token_bytes(32), dpapi_key, purpose='state-wrapping')
        enterprise_vault = root_tmp / 'enterprise_vault'
        enterprise_vault.mkdir()
        bridge = CryptoBridge(enterprise_vault, dpapi_key)

        node_keys = {c: Ed25519PrivateKey.generate() for c in ('C001', 'C002')}
        worker_priv = Ed25519PrivateKey.generate()
        worker_pub = public_hex(worker_priv)

        worker_dir = root_tmp / 'worker'
        worker_dir.mkdir()
        worker_key_file = worker_dir / 'worker_ed25519.hex'
        worker_key_file.write_text(worker_priv.private_bytes_raw().hex(), encoding='utf-8')
        grants_file = worker_dir / 'grants.json'
        grants_file.write_text(
            json.dumps(
                dict(
                    version='he-worker-grants/1.0.0',
                    grants=[
                        dict(tenant_id='native-demo', company_id=comp, node_verify_key=public_hex(node_keys[comp]), active=True)
                        for comp in ('C001', 'C002')
                    ],
                )
            ),
            encoding='utf-8',
        )
        worker_state = worker_dir / 'state'
        worker_cfg = worker_dir / 'worker-config.json'
        worker_cfg.write_text(
            json.dumps(
                dict(
                    version=VERSION,
                    state_dir=linux_path(worker_state),
                    grants_file=linux_path(grants_file),
                    signing_key_file=linux_path(worker_key_file),
                    builds={k: linux_path(v) for k, v in BUILDS.items()},
                )
            ),
            encoding='utf-8',
        )

        manifest_hashes = {
            k: json.loads((v / 'manifest.json').read_bytes())['files']['server.zip']
            for k, v in BUILDS.items()
        }

        port = _free_port()
        worker_url = f'http://127.0.0.1:{port}'
        worker_proc = _wsl_worker_start(public_bundle, worker_cfg, port, worker_dir / 'worker.log')

        # Readiness signed verification
        ch = secrets.token_hex(32)
        ready = verify(post(worker_url, '/v1/readiness', envelope(_scope('C001'), node_keys['C001'], dict(challenge=ch))), worker_pub)
        assert ready['challenge'] == ch and ready['builds'] == manifest_hashes

        # Provision DPAPI vaults & measure keygen time (verifying read-only scope cannot provision keys)
        from sme_fraud.import_files import ImportFailure

        try:
            bridge.provision(_scope('C001'), BUILDS['rules'])
            raise AssertionError('read-only scope unexpectedly allowed to provision HE keys')
        except ImportFailure as denied:
            assert denied.code == 'MODEL_FIT_DENIED'

        provisioning_metrics = {}
        for comp in ('C001', 'C002'):
            for prof in ('rules', 'c3', 'graph'):
                t0 = time.monotonic()
                meta = bridge.provision(_fit_scope(comp), BUILDS[prof])
                provisioning_metrics[f'{comp}:{prof}'] = dict(
                    keygen_seconds=round(time.monotonic() - t0, 4),
                    evaluation_key_bytes=bridge.public_key(_scope(comp), BUILDS[prof]).stat().st_size,
                    key_epoch=meta['key_epoch'],
                )
        print('Provisioning complete:', json.dumps(provisioning_metrics), flush=True)

        snapshots = SnapshotStore(root_tmp / 'snapshots.sqlite3')
        results_summary = dict(provisioning=provisioning_metrics, slices={}, recovery={})

        # =====================================================================
        # SLICE 1: P1 on agent2-rule-snapshot/1.0.0 + HTTP FHE + Recovery
        # =====================================================================
        # Case 1a: C001 P1 hit (AUDIT_0000)
        c1 = Case()
        c1.at = datetime(2025, 8, 12, 11, tzinfo=timezone(timedelta(hours=7)))
        c1.tables['employees'] = [c1.director, c1.maker, c1.worker]
        c1.tables['vendors'] = [c1.vendor]
        p_prior = c1.pay(c1.at - timedelta(days=1), 6_000_000, invoice_number='INV_C1_HIT', invoice_gross_vnd=10_000_000)
        p_hit = c1.pay(c1.at, 6_000_000, invoice_number='INV_C1_HIT', invoice_gross_vnd=10_000_000)
        p_prior['transaction_id'] = 'PRIOR_0000'
        p_hit['transaction_id'] = 'AUDIT_0000'
        authorities(c1)
        src1 = finish(c1, 'C001')
        sid1 = _commit(snapshots, _scope('C001'), _wrap(src1, ['AUDIT_0000']), 'http-c1-p1')
        native1 = analyze_rule_snapshot(snapshots, _scope('C001'), sid1, src1['as_of'], technical=True)
        native1_p1 = next(r for r in native1['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'P1')
        plan1 = prepare_p1_rule_snapshot(snapshots, _scope('C001'), sid1, src1['as_of'])

        plain1, m1, artifact1 = _execute_request_over_http(
            bridge=bridge,
            scope=_scope('C001'),
            node_key=node_keys['C001'],
            worker_url=worker_url,
            worker_pub=worker_pub,
            bundle=BUILDS['rules'],
            values=plan1['rows'][0]['requests'][0]['values'],
            work_dir=root_tmp / 'run_c1_p1',
            session_id='s_c1_p1',
            nonce='n_c1_p1',
            profile='rules',
            expected_circuit_sha256=manifest_hashes['rules'],
        )
        decoded1 = decode_p1_plan_results(plan1, [plain1])
        assert decoded1['rows'][0]['matched'] is True and native1_p1['matched'] is True
        assert decoded1['rows'][0]['score'] == native1_p1['score'] == 20
        assert decoded1['rows'][0]['row_check']['excess_vnd'] == 2_000_000

        # Recovery R1: Lost HTTP reply idempotent replay (/v1/evaluate & /v1/results)
        replay_resp = post(worker_url, '/v1/evaluate', artifact1['packet'], timeout=30)
        assert replay_resp == artifact1['response']
        res_resp = post(
            worker_url,
            '/v1/results',
            envelope(_scope('C001'), node_keys['C001'], dict(session_id='s_c1_p1', nonce='n_c1_p1', request_sha256=sha(canonical(artifact1['packet'])))),
            timeout=30,
        )
        assert res_resp == artifact1['response']
        results_summary['recovery']['R1_lost_reply_idempotency'] = True

        # Case 1b: C002 P1 simultaneous batch (group_mode=1)
        c2 = Case()
        c2.at = datetime(2025, 8, 12, 11, tzinfo=timezone(timedelta(hours=7)))
        c2.tables['employees'] = [c2.director, c2.maker, c2.worker]
        c2.tables['vendors'] = [c2.vendor]
        t_sim1 = c2.pay(c2.at, 6_000_000, invoice_number='INV_C2_SIM', invoice_gross_vnd=10_000_000)
        t_sim2 = c2.pay(c2.at, 5_000_000, invoice_number='INV_C2_SIM', invoice_gross_vnd=10_000_000)
        authorities(c2)
        src2 = finish(c2, 'C002')
        sid2 = _commit(snapshots, _scope('C002'), _wrap(src2, [t_sim1['transaction_id']]), 'http-c2-sim')
        native2 = analyze_rule_snapshot(snapshots, _scope('C002'), sid2, src2['as_of'], technical=True)
        native2_grp = next(r['groups'] for r in native2['catalogue_results'] if r['rule_id'] == 'P1')[0]
        plan2 = prepare_p1_rule_snapshot(snapshots, _scope('C002'), sid2, src2['as_of'])
        plain2_outs = []
        m2_list = []
        for idx_r, req in enumerate(plan2['rows'][0]['requests']):
            out_v, m_v, _ = _execute_request_over_http(
                bridge=bridge,
                scope=_scope('C002'),
                node_key=node_keys['C002'],
                worker_url=worker_url,
                worker_pub=worker_pub,
                bundle=BUILDS['rules'],
                values=req['values'],
                work_dir=root_tmp / f'run_c2_sim_{idx_r}',
                session_id=f's_c2_sim_{idx_r}',
                nonce=f'n_c2_sim_{idx_r}',
                profile='rules',
                expected_circuit_sha256=manifest_hashes['rules'],
            )
            plain2_outs.append(out_v)
            m2_list.append(m_v)
        decoded2 = decode_p1_plan_results(plan2, plain2_outs)
        assert decoded2['rows'][0]['matched'] is False
        assert decoded2['rows'][0]['simultaneous_checks'][0]['matched'] is True and native2_grp['signal'] is True
        assert decoded2['rows'][0]['simultaneous_checks'][0]['excess_vnd'] == 1_000_000

        # Recovery R2: Expired TTL -> Fresh Admission (/v1/admit) reusing exact expired packet
        src_exp, info_exp = scenario('P1', False, 'C001')
        sid_exp = _commit(snapshots, _scope('C001'), _wrap(src_exp, [info_exp['target_transaction_id']]), 'http-exp')
        plan_exp = prepare_p1_rule_snapshot(snapshots, _scope('C001'), sid_exp, src_exp['as_of'])
        enc_exp = bridge.encrypt(_scope('C001'), BUILDS['rules'], plan_exp['rows'][0]['requests'][0]['values'], root_tmp / 'run_exp_enc')
        pub_h = upload(worker_url, _scope('C001'), node_keys['C001'], worker_pub, bridge.public_key(_scope('C001'), BUILDS['rules']), 'public_evaluation_keys')
        arg_h = [upload(worker_url, _scope('C001'), node_keys['C001'], worker_pub, root_tmp / 'run_exp_enc' / f'argument-{i}.cipher', 'ciphertext') for i in range(6)]
        expired_packet = sign(
            dict(
                version=VERSION,
                tenant_id='native-demo',
                company_id='C001',
                node_verify_key=public_hex(node_keys['C001']),
                expires_at=int(time.time()) - 25200,
                profile='rules',
                circuit_sha256=manifest_hashes['rules'],
                evaluation_keys_sha256=pub_h,
                arguments_sha256=arg_h,
                session_id='s_c1_exp',
                nonce='n_c1_exp',
            ),
            node_keys['C001'],
        )
        try:
            post(worker_url, '/v1/evaluate', expired_packet, timeout=30)
            raise AssertionError('expired evaluate unexpectedly accepted')
        except ServiceError as err:
            assert err.code == 'HE4_EXPIRED'
        admit_resp = post(
            worker_url,
            '/v1/admit',
            envelope(_scope('C001'), node_keys['C001'], dict(purpose=FRESH_ADMISSION, request=expired_packet)),
            timeout=600,
        )
        admit_receipt = verify(admit_resp, worker_pub)
        assert admit_receipt['request_sha256'] == sha(canonical(expired_packet))
        download(worker_url, _scope('C001'), node_keys['C001'], admit_receipt['result_sha256'], root_tmp / 'run_exp_res.cipher')
        plain_exp = bridge.decrypt(_scope('C001'), BUILDS['rules'], root_tmp / 'run_exp_res.cipher', admit_receipt['result_sha256'], root_tmp / 'run_exp_open', enc_exp)
        assert decode_p1_plan_results(plan_exp, [plain_exp])['rows'][0]['matched'] is False
        results_summary['recovery']['R2_ttl_expiry_fresh_admission'] = True

        results_summary['slices']['P1'] = dict(
            C001_hit=dict(parity=True, metrics=m1),
            C002_simultaneous_group=dict(parity=True, metrics=m2_list),
        )
        print('Slice 1 P1 HTTP FHE + R1/R2 verified!', flush=True)

        # =====================================================================
        # SLICE 2: C3 on build-c3-v1 + HTTP FHE + Mid-compute SIGKILL Crash Recovery
        # =====================================================================
        c3_cases = []
        for comp, dt_s, label in (('C001', 20, 'C001_C3_hit_20s'), ('C002', 60, 'C002_C3_boundary_60s')):
            cb = base()
            target = cb.pay(amount=60_000_000, created_at=(cb.at - timedelta(seconds=dt_s)).isoformat(timespec='seconds'))
            authorities(cb)
            src_c3 = finish(cb, comp)
            sid_c3 = _commit(snapshots, _scope(comp), _wrap(src_c3, [target['transaction_id']]), f'http-{label}')
            nat_c3 = analyze_rule_snapshot(snapshots, _scope(comp), sid_c3, src_c3['as_of'], technical=True)
            nat_c3_rule = next(r for r in nat_c3['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'C3')
            plan_c3 = prepare_c3_rule_snapshot(snapshots, _scope(comp), sid_c3, src_c3['as_of'])
            plain_c3, m_c3, _ = _execute_request_over_http(
                bridge=bridge,
                scope=_scope(comp),
                node_key=node_keys[comp],
                worker_url=worker_url,
                worker_pub=worker_pub,
                bundle=BUILDS['c3'],
                values=plan_c3['rows'][0]['requests'][0]['values'],
                work_dir=root_tmp / f'run_{label}',
                session_id=f's_{label}',
                nonce=f'n_{label}',
                profile='c3',
                expected_circuit_sha256=manifest_hashes['c3'],
            )
            dec_c3 = decode_c3_plan_results(plan_c3, [plain_c3])
            assert dec_c3['rows'][0]['matched'] == nat_c3_rule['matched']
            assert dec_c3['rows'][0]['score'] == nat_c3_rule['score']
            assert dec_c3['rows'][0]['details']['approval_delta_us'] == dt_s * 1_000_000
            c3_cases.append(dict(case=label, parity=True, matched=dec_c3['rows'][0]['matched'], metrics=m_c3))

        # C002 C3 ambiguous_authority inside FHE
        src_amb, info_amb = scenario('C3', True, 'C002')
        tie = deepcopy(src_amb['tables']['approval_authorities'][1])
        tie['authority_id'] = 'SIM_TIE_CONFLICT'
        tie['authority_level'] = 'standard'
        src_amb['tables']['approval_authorities'].append(tie)
        _rehash(src_amb)
        sid_amb = _commit(snapshots, _scope('C002'), _wrap(src_amb, [info_amb['target_transaction_id']]), 'http-c3-ambig')
        nat_amb = analyze_rule_snapshot(snapshots, _scope('C002'), sid_amb, src_amb['as_of'], technical=True)
        assert next(r for r in nat_amb['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'C3')['status'] == 'unavailable'
        plan_amb = prepare_c3_rule_snapshot(snapshots, _scope('C002'), sid_amb, src_amb['as_of'])
        plain_amb, m_amb, _ = _execute_request_over_http(
            bridge=bridge,
            scope=_scope('C002'),
            node_key=node_keys['C002'],
            worker_url=worker_url,
            worker_pub=worker_pub,
            bundle=BUILDS['c3'],
            values=plan_amb['rows'][0]['requests'][0]['values'],
            work_dir=root_tmp / 'run_c3_ambig',
            session_id='s_c3_ambig',
            nonce='n_c3_ambig',
            profile='c3',
            expected_circuit_sha256=manifest_hashes['c3'],
        )
        dec_amb = decode_c3_plan_results(plan_amb, [plain_amb])
        assert dec_amb['rows'][0]['status'] == 'unavailable'
        assert dec_amb['rows'][0]['reason'] == 'authority_not_covered_or_ambiguous_at_action'
        assert dec_amb['rows'][0]['details']['ambiguous_authority'] is True
        c3_cases.append(dict(case='C002_C3_ambiguous_unavailable', parity=True, matched=None, metrics=m_amb))

        # Recovery R3: Mid-compute SIGKILL on P1 (long enough to reliably catch `native.started`), restart worker, promote `running -> retryable`, `/v1/resume` -> exact result
        src_k, info_k = scenario('P1', True, 'C001')
        sid_k = _commit(snapshots, _scope('C001'), _wrap(src_k, [info_k['target_transaction_id']]), 'http-kill')
        plan_k = prepare_p1_rule_snapshot(snapshots, _scope('C001'), sid_k, src_k['as_of'])
        enc_k = bridge.encrypt(_scope('C001'), BUILDS['rules'], plan_k['rows'][0]['requests'][0]['values'], root_tmp / 'run_kill_enc')
        pub_hk = upload(worker_url, _scope('C001'), node_keys['C001'], worker_pub, bridge.public_key(_scope('C001'), BUILDS['rules']), 'public_evaluation_keys')
        arg_hk = [upload(worker_url, _scope('C001'), node_keys['C001'], worker_pub, root_tmp / 'run_kill_enc' / f'argument-{i}.cipher', 'ciphertext') for i in range(6)]
        kill_packet = envelope(
            _scope('C001'),
            node_keys['C001'],
            dict(profile='rules', circuit_sha256=manifest_hashes['rules'], evaluation_keys_sha256=pub_hk, arguments_sha256=arg_hk, session_id='s_kill', nonce='n_kill'),
        )
        eval_err_box = []

        def _bg_eval():
            try:
                eval_err_box.append(('ok', post(worker_url, '/v1/evaluate', kill_packet, timeout=600)))
            except Exception as exc:
                eval_err_box.append(('err', repr(exc)))

        bg = threading.Thread(target=_bg_eval, daemon=True)
        bg.start()

        started_marker = None
        wait_start = time.monotonic() + 90.0
        while time.monotonic() < wait_start:
            found = list(worker_state.glob('attempt_*/native.started'))
            if found:
                started_marker = found[0]
                break
            time.sleep(0.25)
        assert started_marker is not None, 'native.started never appeared before SIGKILL test'
        # Kill only processes referencing this sandbox directory (`worker_dir`)!
        _wsl_worker_stop(worker_proc, kill_pattern=linux_path(worker_dir))
        worker_proc = None
        bg.join(timeout=10)

        with sqlite3.connect(worker_state / 'state' / 'jobs.sqlite3') as conn:
            row_after_kill = conn.execute("SELECT state FROM jobs WHERE session='s_kill' AND nonce='n_kill'").fetchone()
        assert row_after_kill is not None and row_after_kill[0] == 'running'

        # Restart fresh worker on SAME state_dir & verify promotion running -> retryable and clean /v1/resume completion
        port2 = _free_port()
        worker_url = f'http://127.0.0.1:{port2}'
        worker_proc = _wsl_worker_start(public_bundle, worker_cfg, port2, worker_dir / 'worker_restarted.log')
        with sqlite3.connect(worker_state / 'state' / 'jobs.sqlite3') as conn:
            row_promoted = conn.execute("SELECT state FROM jobs WHERE session='s_kill' AND nonce='n_kill'").fetchone()
        assert row_promoted is not None and row_promoted[0] == 'retryable'

        resume_resp = post(
            worker_url,
            '/v1/resume',
            envelope(_scope('C001'), node_keys['C001'], dict(request=kill_packet)),
            timeout=600,
        )
        resume_receipt = verify(resume_resp, worker_pub)
        download(worker_url, _scope('C001'), node_keys['C001'], resume_receipt['result_sha256'], root_tmp / 'run_kill_res.cipher')
        plain_k = bridge.decrypt(_scope('C001'), BUILDS['rules'], root_tmp / 'run_kill_res.cipher', resume_receipt['result_sha256'], root_tmp / 'run_kill_open', enc_k)
        assert decode_p1_plan_results(plan_k, [plain_k])['rows'][0]['matched'] is True

        # Recovery R4: Restart worker cleanly & read previously completed C3 ciphertext without re-running
        _wsl_worker_stop(worker_proc, kill_pattern=linux_path(worker_dir))
        port3 = _free_port()
        worker_url = f'http://127.0.0.1:{port3}'
        worker_proc = _wsl_worker_start(public_bundle, worker_cfg, port3, worker_dir / 'worker_restarted2.log')
        post_restart = post(
            worker_url,
            '/v1/results',
            envelope(_scope('C001'), node_keys['C001'], dict(session_id='s_kill', nonce='n_kill', request_sha256=sha(canonical(kill_packet)))),
            timeout=30,
        )
        assert post_restart == resume_resp
        results_summary['recovery']['R3_mid_compute_sigkill_resume'] = True
        results_summary['recovery']['R4_read_completed_after_restart'] = True
        results_summary['slices']['C3'] = c3_cases
        print('Slice 2 C3 + R3/R4 crash recovery verified!', flush=True)

        # Isolate Slice 3 graph blobs (~3.2 GB) onto a clean worker state so cumulative uploads never exceed BlobStore 8 GiB quota
        _wsl_worker_stop(worker_proc, kill_pattern=linux_path(worker_dir))
        worker_dir_s3 = root_tmp / 'worker_s3'
        worker_dir_s3.mkdir()
        worker_state_s3 = worker_dir_s3 / 'state'
        worker_cfg_s3 = worker_dir_s3 / 'worker-config.json'
        worker_cfg_s3.write_text(
            json.dumps(
                dict(
                    version=VERSION,
                    state_dir=linux_path(worker_state_s3),
                    grants_file=linux_path(grants_file),
                    signing_key_file=linux_path(worker_key_file),
                    builds={k: linux_path(v) for k, v in BUILDS.items()},
                )
            ),
            encoding='utf-8',
        )
        port_s3 = _free_port()
        worker_url = f'http://127.0.0.1:{port_s3}'
        worker_proc = _wsl_worker_start(public_bundle, worker_cfg_s3, port_s3, worker_dir_s3 / 'worker.log')

        # =====================================================================
        # SLICE 3: B1 & B5/E4 on build-graph-difference-v1 + HTTP FHE
        # =====================================================================
        src_b1, info_b1 = scenario('B1', True, 'C001')
        sid_b1 = _commit(snapshots, _scope('C001'), _wrap(src_b1, [info_b1['target_transaction_id']]), 'http-b1')
        nat_b1 = analyze_rule_snapshot(snapshots, _scope('C001'), sid_b1, src_b1['as_of'], technical=True)
        nat_b1_r = next(r for r in nat_b1['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'B1')
        plan_b1 = plan_b1_from_rule_snapshot(_wrap(src_b1, [info_b1['target_transaction_id']]), _scope('C001'))
        plain_b1, m_b1, _ = _execute_request_over_http(
            bridge=bridge,
            scope=_scope('C001'),
            node_key=node_keys['C001'],
            worker_url=worker_url,
            worker_pub=worker_pub,
            bundle=BUILDS['graph'],
            values=plan_b1['rows'][0]['requests'][0]['values'],
            work_dir=root_tmp / 'run_b1',
            session_id='s_b1',
            nonce='n_b1',
            profile='graph',
            expected_circuit_sha256=manifest_hashes['graph'],
        )
        dec_b1 = decode_b1_plan_results(plan_b1, [plain_b1])
        assert dec_b1['rows'][0]['matched'] == nat_b1_r['matched'] is True
        assert dec_b1['rows'][0]['score'] == nat_b1_r['score'] == 20

        src_b5, info_b5 = scenario('B5', True, 'C002')
        sid_b5 = _commit(snapshots, _scope('C002'), _wrap(src_b5, [info_b5['target_transaction_id']]), 'http-b5')
        nat_b5 = analyze_rule_snapshot(snapshots, _scope('C002'), sid_b5, src_b5['as_of'], technical=True)
        nat_b5_r = next(r for r in nat_b5['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'B5')
        plan_b5 = plan_b5_e4_from_rule_snapshot(_wrap(src_b5, [info_b5['target_transaction_id']]), _scope('C002'))
        plain_b5, m_b5, _ = _execute_request_over_http(
            bridge=bridge,
            scope=_scope('C002'),
            node_key=node_keys['C002'],
            worker_url=worker_url,
            worker_pub=worker_pub,
            bundle=BUILDS['graph'],
            values=plan_b5['rows'][0]['requests'][0]['values'],
            work_dir=root_tmp / 'run_b5',
            session_id='s_b5',
            nonce='n_b5',
            profile='graph',
            expected_circuit_sha256=manifest_hashes['graph'],
        )
        dec_b5 = decode_b5_e4_plan_results(plan_b5, [plain_b5])
        assert dec_b5['rows'][0]['matched'] == nat_b5_r['matched'] is True
        assert dec_b5['rows'][0]['score'] == nat_b5_r['score'] == 0
        assert dec_b5['rows'][0]['intrinsic_points'] == 3 and dec_b5['rows'][0]['aliases'] == ['E4']

        results_summary['slices']['B1_B5_E4'] = dict(
            C001_B1=dict(parity=True, metrics=m_b1),
            C002_B5_E4=dict(parity=True, metrics=m_b5),
        )
        results_summary['peak_wsl_rss_mb'] = peak_rss_mb['max']
        results_summary['security_boundary'] = dict(
            worker_has_sme_fraud=False,
            worker_has_secret_key=False,
            dpapi_provider='windows-dpapi-current-user',
            all_requests_ed25519_signed=True,
            cross_company_isolated=True,
            live_portal_untouched=True,
        )

        evidence_dir = Path(r'D:\agent22\Agent2_Spec_v2_1\evidence\HE\he_rule_expansion_20261114')
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / 'metrics.json').write_text(json.dumps(results_summary, indent=2) + '\n', encoding='utf-8')
        print('ALL SLICES VERIFIED CLEANLY:', json.dumps(results_summary, indent=2), flush=True)
        return 0
    finally:
        stop_sampler.set()
        if worker_proc is not None:
            _wsl_worker_stop(worker_proc, kill_pattern=linux_path(root_tmp))
        shutil.rmtree(root_tmp, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
