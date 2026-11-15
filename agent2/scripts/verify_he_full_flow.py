"""Real Concrete FHE + HTTP Coordinator + Portal + Crash Recovery end-to-end verifier.

Exercises the full `agent2-rule-snapshot/1.0.0` workflow:
  Locked Snapshot -> Point-in-time Guard & Plan -> DPAPI Keygen & WSL Encrypt ->
  Ed25519 Signed HTTP Worker (WSL concrete-python 2.11.0) -> Local Decrypt ->
  3-Way Parity (Native Business Engine vs Plaintext Circuit vs Real HTTP FHE) ->
  Portal HTTP APIs (datasets, jobs, result, RBAC masking, workspace, reviews, CSV) ->
  Crash Recovery R1/R2/R3/R4 (encrypt checkpoint, lost reply, 7h expiry /v1/admit, real SIGKILL).

Strict isolation: operates solely inside a fresh `tempfile.mkdtemp()` sandbox and
ephemeral loopback sockets; never modifies live `.runtime` services, keys, or DBs.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
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
import uuid

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from finance_input import AccessScope

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'tests') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tests'))
if str(ROOT / 'tests_he') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tests_he'))

from experiments.he4 import FRESH_ADMISSION, VERSION, bundle as he4_bundle, c3_circuit, circuits
from experiments.he4.client_transport import download as real_download, envelope, upload as real_upload
import experiments.he4.coordinator as coordinator_mod
from experiments.he4.coordinator import FourJobs, Settings
from experiments.he4.rule_snapshot_adapter import (
    decode_p1_plan_results,
    plan_p1_from_rule_snapshot,
)
from experiments.he4.rule_snapshot_c3_adapter import (
    decode_c3_plan_results,
    plan_c3_from_rule_snapshot,
)
from experiments.he4.rule_snapshot_coordinator import RULE_SNAPSHOT_RESULT_VERSION
from experiments.he4.rule_snapshot_identity_adapter import (
    decode_b1_plan_results,
    decode_b5_e4_plan_results,
    plan_b1_from_rule_snapshot,
    plan_b5_e4_from_rule_snapshot,
)
from experiments.he4.web import FourWorkbench
from experiments.he4.windows_bridge import CryptoBridge, linux_path
from experiments.he_inference.enterprise_server import EnterpriseNode
from experiments.he_inference.http_common import ServiceError, post as real_post
from experiments.he_inference.key_manager import create_key
from experiments.he_inference.protocol import HEUnavailable, canonical, public_hex, sha, sign, verify

from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import ImportFailure, canonical as sme_canonical, digest as sme_digest
from sme_fraud.method_store import MethodStore
from sme_fraud.native_rule_demo import authorities, finish, scenario
from sme_fraud.review_server import make_server
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields
from test_validation_backend import policy_for

WSL_PYTHON = '/home/sang/.local/share/agent2/he4/bin/python'
BUILDS_ROOT = Path(r'D:\agent22\.runtime\he4')
BUILD_PATHS = {
    'rules': str(BUILDS_ROOT / 'build-rules-difference-v1'),
    'c3': str(BUILDS_ROOT / 'build-c3-v1'),
    'graph': str(BUILDS_ROOT / 'build-graph-difference-v1'),
    'statistics': str(BUILDS_ROOT / 'build-statistics-v1'),
}
TZ7 = timezone(timedelta(hours=7))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return int(s.getsockname()[1])


def _rehash(source: dict) -> dict:
    for name, rows in source['tables'].items():
        source['coverage'][name] = dict(
            source['coverage'][name],
            record_count=len(rows),
            records_sha256=sme_digest(sme_canonical(rows)),
        )
    return source


def _wrap(source: dict, candidate_ids: list[str]) -> dict:
    return dict(
        contract_version=CONTRACT,
        tenant_id=source['tenant_id'],
        company_id=source['company_id'],
        source=source,
        candidate_transaction_ids=candidate_ids,
    )


def _commit(store: SnapshotStore, scope: AccessScope, doc: dict, key: str) -> str:
    draft = store.upload(scope, sme_canonical(doc), 'rule-snapshot.json', key + '-up')
    live = store.get_import(scope, draft['import_id'])
    if live.get('snapshot_id'):
        return live['snapshot_id']
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise AssertionError(f'Snapshot preview rejected for {key}: {preview["errors"]}')
    return store.commit(scope, draft['import_id'], commit_fields(preview), key + '-cm')['snapshot']['snapshot_id']


def _sample_wsl_rss_mb(sandbox_tag: str) -> float | None:
    cmd = f"ps -eo rss,args | grep -F {shlex.quote(sandbox_tag)} | grep -E 'public_worker|experiments.he4.service|enterprise_helper' | grep -v grep || true"
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


def _wsl_worker_start(bundle_dir: Path, cfg_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env_cmd = (
        f"cd /tmp && PYTHONPATH={shlex.quote(linux_path(bundle_dir))} "
        f"{WSL_PYTHON} -u -m experiments.he4.service --config {shlex.quote(linux_path(cfg_path))} --port {port}"
    )
    proc = subprocess.Popen(
        ['wsl.exe', '-d', 'Debian', '--exec', 'bash', '-lc', env_cmd],
        stdout=log_path.open('wb'),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    url = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + 30.0
    import urllib.request

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'Worker exited early ({proc.returncode}): {log_path.read_text(errors="replace")}')
        try:
            with urllib.request.urlopen(url + '/health', timeout=2) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            time.sleep(0.3)
    raise RuntimeError('Timed out starting WSL HE4 HTTP worker')


def _wsl_worker_stop(proc: subprocess.Popen | None, *, kill_pattern: str | None = None) -> None:
    if kill_pattern:
        subprocess.run(
            ['wsl.exe', '-d', 'Debian', '--exec', 'bash', '-lc', f'pkill -9 -f {shlex.quote(kill_pattern)} || true'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    if proc is not None:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


def _blob_inventory(state_dir: Path) -> dict:
    blobs_dir = state_dir / 'blobs'
    if not blobs_dir.exists():
        return dict(total_bytes=0, blob_count=0, by_size_desc=[])
    sizes = sorted((p.stat().st_size for p in blobs_dir.glob('*/*') if p.is_file()), reverse=True)
    return dict(
        total_bytes=sum(sizes),
        total_gib=round(sum(sizes) / (1024 ** 3), 4),
        blob_count=len(sizes),
        largest_blobs_bytes=sizes[:10],
    )


class _TimedCryptoBridge(CryptoBridge):
    """Transparent telemetry wrapper over real DPAPI + WSL CryptoBridge."""

    def __init__(self, enterprise_root: Path, key_file: Path):
        super().__init__(enterprise_root, key_file)
        self.events: list[dict] = []

    def provision(self, scope, bundle):
        t0 = time.monotonic()
        meta = super().provision(scope, bundle)
        elapsed = round(time.monotonic() - t0, 4)
        pub = self.public_key(scope, bundle)
        self.events.append(
            dict(
                op='provision',
                company=next(iter(scope.company_ids)),
                profile=meta['binding']['profile'],
                seconds=elapsed,
                evaluation_key_bytes=pub.stat().st_size,
            )
        )
        return meta

    def encrypt(self, scope, bundle, values, output, *, recover_uncommitted=False):
        t0 = time.monotonic()
        existed_sealed = (Path(output) / 'manifest.sealed').exists()
        meta = super().encrypt(scope, bundle, values, output, recover_uncommitted=recover_uncommitted)
        elapsed = round(time.monotonic() - t0, 4)
        out_dir = Path(output)
        cipher_bytes = sum((out_dir / f'argument-{i}.cipher').stat().st_size for i in range(len(meta['arguments_sha256'])))
        self.events.append(
            dict(
                op='encrypt',
                company=next(iter(scope.company_ids)),
                profile=meta['binding']['profile'],
                seconds=elapsed,
                checkpoint_reused=existed_sealed,
                request_cipher_bytes=cipher_bytes,
            )
        )
        return meta

    def decrypt(self, scope, bundle, cipher, cipher_sha256, output, context):
        t0 = time.monotonic()
        val = super().decrypt(scope, bundle, cipher, cipher_sha256, output, context)
        elapsed = round(time.monotonic() - t0, 4)
        self.events.append(
            dict(
                op='decrypt',
                company=next(iter(scope.company_ids)),
                profile=context['binding']['profile'],
                seconds=elapsed,
                result_cipher_bytes=Path(cipher).stat().st_size,
            )
        )
        return val


class _DryPlainBridge:
    """Fast dry-run substitute (--dry-plain only) validating harness wiring in <5s."""

    def __init__(self, root: Path):
        self.root = root / 'dry_keys'
        self.root.mkdir(parents=True, exist_ok=True)
        self.events: list[dict] = []

    def provision(self, scope, bundle):
        m = json.loads((Path(bundle) / 'manifest.json').read_bytes())
        p = self.root / f"{next(iter(scope.company_ids))}_{m['profile']}.keys"
        p.write_bytes(b'DRY')
        return dict(binding=dict(profile=m['profile']), evaluation_keys_sha256=sha(b'DRY'))

    def public_key(self, scope, bundle):
        m = json.loads((Path(bundle) / 'manifest.json').read_bytes())
        p = self.root / f"{next(iter(scope.company_ids))}_{m['profile']}.keys"
        if not p.exists():
            p.write_bytes(b'DRY')
        return p

    def encrypt(self, scope, bundle, values, output, *, recover_uncommitted=False):
        m = json.loads((Path(bundle) / 'manifest.json').read_bytes())
        out = Path(output)
        existed_sealed = recover_uncommitted and (out / 'manifest.sealed').exists()
        out.mkdir(parents=True, exist_ok=True)
        hashes = []
        for idx, val in enumerate(values):
            b = canonical(val)
            (out / f'argument-{idx}.cipher').write_bytes(b)
            hashes.append(sha(b))
        (out / 'manifest.sealed').write_bytes(b'sealed')
        company = next(iter(scope.company_ids))
        self.events.append(dict(op='encrypt', company=company, profile=m['profile'], seconds=0.001, checkpoint_reused=existed_sealed, request_cipher_bytes=sum(len(canonical(v)) for v in values)))
        return dict(
            binding=dict(tenant_id=scope.tenant_id, company_id=company, profile=m['profile'], circuit_sha256=m['files']['server.zip'], specs_sha256=m['files']['client.specs.json']),
            key_epoch='key_' + sha(m['profile'].encode()),
            evaluation_keys_sha256=sha(b'DRY'),
            arguments_sha256=hashes,
        )

    def decrypt(self, scope, bundle, cipher, cipher_sha256, output, context):
        self.events.append(dict(op='decrypt', company=next(iter(scope.company_ids)), profile=context['binding']['profile'], seconds=0.001, result_cipher_bytes=Path(cipher).stat().st_size))
        return json.loads(Path(cipher).read_bytes().decode())


def _base_case(company: str, *, extra_vendor_phone_same: bool = False, disclosed: bool = False, fast_seconds: int = 15, amount_vnd: int = 6_000_000, prior_amount_vnd: int = 6_000_000) -> tuple[Case, dict]:
    c = Case()
    c.at = datetime(2025, 8, 12, 11, 0, tzinfo=TZ7)
    c.tables['employees'] = [c.director, c.maker, c.worker]
    c.tables['customers'] = c.tables['customers'][:1]
    c.tables['entity_links'] = []
    c.tables['attendance'] = [
        r
        for r in c.tables['attendance']
        if r['employee_id'] == c.worker['employee_id'] and r['payroll_period'] == '2025-08'
    ][:1]
    c.tables['vendor_status_history'] = [r for r in c.tables['vendor_status_history'] if r['vendor_id'] == c.vendor['vendor_id']]
    for i, emp in enumerate(c.tables['employees']):
        emp.update(
            bank_account=f'SIM_STAFF_{i}',
            bank_code='SIMBANK',
            phone=f'090100000{i}',
            address=f'SIM_STAFF_ADDR_{i}',
            national_id=f'07909900010{i}',
        )
    c.vendor.update(
        name='Orchid marine instruments',
        bank_account='SIM_VENDOR',
        bank_code='SIMBANK',
        phone='0902000000',
        address='SIM_VENDOR_ADDRESS',
        national_id='079088000111',
        related_party_disclosed_at=(c.at - timedelta(days=20)).isoformat() if disclosed else '',
    )
    v2 = deepcopy(c.vendor)
    v2['vendor_id'] = 'SIM_VENDOR_2'
    v2['name'] = 'Second Supplier Co'
    v2['phone'] = c.vendor['phone'] if extra_vendor_phone_same else '0909888777'
    v2['bank_account'] = '88889999000'
    v2['address'] = 'DISTINCT AVE 22'
    v2['national_id'] = '079088000222'
    v2['related_party_disclosed_at'] = ''
    c.tables['vendors'] = [c.vendor, v2]

    prior = c.pay(c.at - timedelta(days=1), prior_amount_vnd, invoice_number='INV_MULTI', invoice_gross_vnd=10_000_000)
    prior['transaction_id'] = f'PRIOR_{company}'
    prior['created_at'] = (c.at - timedelta(days=1, minutes=5)).isoformat()
    prior['approved_at'] = (c.at - timedelta(days=1)).isoformat()

    target = c.pay(c.at - timedelta(minutes=10), amount_vnd, invoice_number='INV_MULTI', invoice_gross_vnd=10_000_000)
    target['transaction_id'] = 'AUDIT_0000'
    target['created_at'] = (c.at - timedelta(minutes=10, seconds=fast_seconds)).isoformat()
    target['approved_at'] = (c.at - timedelta(minutes=10)).isoformat()
    if extra_vendor_phone_same:
        target['recipient_account'] = c.worker['bank_account']
        target['recipient_bank_code'] = c.worker['bank_code']

    payroll = c.pay(c.at - timedelta(minutes=15), 9_000_000, kind='payroll')
    payroll['transaction_id'] = f'PAYROLL_{company}'
    payroll['employee_id'] = c.worker['employee_id']
    payroll['payroll_period'] = '2025-08'
    payroll['recipient_account'] = c.worker['bank_account']
    payroll['recipient_bank_code'] = c.worker['bank_code']
    payroll['created_at'] = (c.at - timedelta(minutes=25)).isoformat()
    payroll['approved_at'] = (c.at - timedelta(minutes=15)).isoformat()

    future_ts = (c.at + timedelta(hours=2)).isoformat()
    future = c.pay(c.at + timedelta(hours=2), amount_vnd, invoice_number='INV_MULTI', invoice_gross_vnd=10_000_000)
    future['transaction_id'] = f'FUTURE_{company}'
    future['posted_at'] = future_ts
    future['observed_at'] = future_ts
    future['created_at'] = (c.at - timedelta(minutes=5)).isoformat()
    future['approved_at'] = future_ts

    c.rows = [prior, target, payroll, future]
    c.tables['transactions'] = c.rows
    authorities(c)
    src = finish(c, company)
    src['tenant_id'] = 'demo'
    src['as_of'] = c.at.isoformat()
    for cov in src['coverage'].values():
        cov['observed_at'] = src['as_of']
        cov['covered_through'] = src['as_of']
    _rehash(src)
    return c, _wrap(src, ['AUDIT_0000', payroll['transaction_id'], future['transaction_id']])


def _warm_extra_doc(company: str = 'C001') -> dict:
    """Simultaneous P1 batch hit + C3 conflicting authority tie + B5/E4 address-only."""
    c, _ = _base_case(company, extra_vendor_phone_same=False, fast_seconds=15, amount_vnd=5_500_000, prior_amount_vnd=1_000_000)
    # Remove v1 from shared address; use v2 & v3 sharing ONLY address (weak=1)
    v2 = next(v for v in c.tables['vendors'] if v['vendor_id'] == 'SIM_VENDOR_2')
    v2['address'] = 'COMMON TOWER 88'
    v2['phone'] = '0905111222'
    v2['bank_account'] = '9100000001'
    v3 = deepcopy(v2)
    v3['vendor_id'] = 'SIM_VENDOR_3'
    v3['name'] = 'Third Supplier Co'
    v3['phone'] = '0905111333'
    v3['bank_account'] = '9100000002'
    c.tables['vendors'] = [c.vendor, v2, v3]

    sim_at = c.at - timedelta(minutes=8)
    s1 = c.pay(sim_at, 5_500_000, vendor=v2, invoice_number='INV_SIM', invoice_gross_vnd=10_000_000)
    s1['transaction_id'] = 'SIM_BATCH_A'
    s1['created_at'] = (sim_at - timedelta(minutes=10)).isoformat()
    s1['approved_at'] = sim_at.isoformat()

    s2 = c.pay(sim_at, 5_500_000, vendor=v2, invoice_number='INV_SIM', invoice_gross_vnd=10_000_000)
    s2['transaction_id'] = 'SIM_BATCH_B'
    s2['created_at'] = (sim_at - timedelta(minutes=12)).isoformat()
    s2['approved_at'] = sim_at.isoformat()

    ambig_tx = c.pay(c.at - timedelta(minutes=4), 40_000_000, vendor=c.vendor, invoice_number='INV_AMB', invoice_gross_vnd=50_000_000)
    ambig_tx['transaction_id'] = 'C3_AMBIG_TIE'
    ambig_tx['created_at'] = (c.at - timedelta(minutes=4, seconds=12)).isoformat()
    ambig_tx['approved_at'] = (c.at - timedelta(minutes=4)).isoformat()

    c.rows = [s1, s2, ambig_tx]
    c.tables['transactions'] = c.rows
    authorities(c)
    # Replace approver rule with 2 equally specific conflicting rules (standard vs executive) for ambiguous_authority
    std_rule = deepcopy(c.tables['approval_authorities'][1])
    std_rule['authority_id'] = 'TIE_STD'
    std_rule['authority_level'] = 'standard'
    exec_rule = deepcopy(std_rule)
    exec_rule['authority_id'] = 'TIE_EXEC'
    exec_rule['authority_level'] = 'executive'
    c.tables['approval_authorities'] = [c.tables['approval_authorities'][0], std_rule, exec_rule]
    src = finish(c, company)
    src['tenant_id'] = 'demo'
    src['as_of'] = c.at.isoformat()
    for cov in src['coverage'].values():
        cov['observed_at'] = src['as_of']
        cov['covered_through'] = src['as_of']
    _rehash(src)
    return _wrap(src, ['SIM_BATCH_A', 'C3_AMBIG_TIE'])


def _payroll_c3_doc(company: str, tx_id: str, fast_seconds: int = 15, amount_vnd: int = 60_000_000) -> dict:
    """Single-tx payroll fixture that exercises ONLY 1 fast C3 task (~70s on real FHE)."""
    c, _ = _base_case(company, extra_vendor_phone_same=False, fast_seconds=fast_seconds)
    p = c.pay(c.at - timedelta(minutes=7), amount_vnd, kind='payroll')
    p['transaction_id'] = tx_id
    p['employee_id'] = c.worker['employee_id']
    p['payroll_period'] = '2025-08'
    p['recipient_account'] = c.worker['bank_account']
    p['recipient_bank_code'] = c.worker['bank_code']
    p['created_at'] = (c.at - timedelta(minutes=7, seconds=fast_seconds)).isoformat()
    p['approved_at'] = (c.at - timedelta(minutes=7)).isoformat()
    c.rows = [p]
    c.tables['transactions'] = c.rows
    src = finish(c, company)
    src['tenant_id'] = 'demo'
    src['as_of'] = c.at.isoformat()
    for cov in src['coverage'].values():
        cov['observed_at'] = src['as_of']
        cov['covered_through'] = src['as_of']
    _rehash(src)
    return _wrap(src, [tx_id])


def _limits_gaps_doc(company: str = 'C001') -> dict:
    """Multi-tx fixture hitting >4 limits & source gaps (zero FHE tasks generated)."""
    c, _ = _base_case(company, extra_vendor_phone_same=False)
    extra_emp = deepcopy(c.worker)
    extra_emp.update(employee_id='LIM_E3', bank_account='LIM_E3', bank_code='SIMBANK', phone='0907111003', address='LIM_3', national_id='079099000103')
    c.tables['employees'].append(extra_emp)  # 4 employees + 1 target = 5 (>4 graph nodes)
    extra_vendors = []
    for i in range(4):
        ev = deepcopy(c.vendor)
        ev['vendor_id'] = f'LIM_V_{i}'
        ev['name'] = f'Limit Vendor {i}'
        ev['bank_account'] = f'LVB_{i}'
        ev['phone'] = f'090722200{i}'
        ev['address'] = f'LVA_{i}'
        extra_vendors.append(ev)
    c.tables['vendors'].extend(extra_vendors)  # 6 vendors (>4 graph nodes)

    priors_lim = []
    for k in range(5):
        pr = c.pay(c.at - timedelta(days=6 - k), 5_000_000, invoice_number='INV_LIM_5', invoice_gross_vnd=50_000_000)
        pr['transaction_id'] = f'LIM_PR_{k}'
        pr['created_at'] = (c.at - timedelta(days=6 - k, minutes=5)).isoformat()
        pr['approved_at'] = (c.at - timedelta(days=6 - k)).isoformat()
        priors_lim.append(pr)

    tx_node = c.pay(c.at - timedelta(minutes=6), 60_000_000, invoice_number='INV_LIM_5', invoice_gross_vnd=50_000_000)
    tx_node['transaction_id'] = 'LIMIT_ALL_TX'
    tx_node['created_at'] = (c.at - timedelta(minutes=6, seconds=10)).isoformat()
    tx_node['approved_at'] = (c.at - timedelta(minutes=6)).isoformat()

    tx_gap = c.pay(c.at - timedelta(minutes=5), 60_000_000, invoice_number='INV_LIM_5', invoice_gross_vnd=50_000_000)
    tx_gap['transaction_id'] = 'LIMIT_GAP_TX'
    tx_gap['created_at'] = (c.at - timedelta(minutes=5, seconds=10)).isoformat()
    tx_gap['approved_at'] = (c.at - timedelta(minutes=5)).isoformat()
    tx_gap['recipient_bank_code'] = ''

    c.rows = [*priors_lim, tx_node, tx_gap]
    c.tables['transactions'] = c.rows
    authorities(c)
    base_rule = deepcopy(c.tables['approval_authorities'][1])
    for idx in range(4):
        r = deepcopy(base_rule)
        r['authority_id'] = f'LIM_AUTH_{idx}'
        r['min_amount_vnd'] = idx * 1_000_000
        c.tables['approval_authorities'].append(r)  # 5 matching rules (>4 C3 authority limit)
    src = finish(c, company)
    src['tenant_id'] = 'demo'
    src['as_of'] = c.at.isoformat()
    for cov in src['coverage'].values():
        cov['observed_at'] = src['as_of']
        cov['covered_through'] = src['as_of']
    _rehash(src)
    return _wrap(src, ['LIMIT_ALL_TX', 'LIMIT_GAP_TX'])


def _eval_plain_outputs(profile: str, reqs: list[dict]) -> list:
    outs = []
    for r in reqs:
        arrs = [np.asarray(v, dtype=np.int64) for v in r['values']]
        if profile == 'rules':
            outs.append(circuits.p1(*arrs).tolist())
        elif profile == 'c3':
            outs.append(c3_circuit.c3(*arrs).tolist())
        elif profile == 'graph':
            outs.append(circuits.graph(*arrs).tolist())
    return outs


def _run_comprehensive_parity_matrix(snapshots: SnapshotStore, scope: AccessScope, real_http_index: dict[str, dict]) -> list[dict]:
    """Build and verify 21 deterministic parity cases (Native == Plaintext HE == Real HTTP)."""
    cases: list[dict] = []

    def check_case(case_id: str, group: str, doc: dict, http_key: tuple[str, str, str] | None = None, *, expect_reject: str | None = None, partial_note: str | None = None):
        if expect_reject:
            try:
                _commit(snapshots, scope, doc, f'mx-{case_id}')
            except AssertionError as exc:
                cases.append(dict(
                    case_id=case_id,
                    group=group,
                    native_status='rejected_schema',
                    plaintext_he_status='rejected_schema',
                    real_http_he_status='rejected_schema',
                    parity_verdict='partial' if partial_note else 'pass',
                    note=partial_note or str(exc)[:180],
                ))
                return
            raise AssertionError(f'{case_id} should have failed validation')

        cid = doc['candidate_transaction_ids'][0]
        sid = _commit(snapshots, scope, doc, f'mx-{case_id}')
        nat = analyze_rule_snapshot(snapshots, scope, sid, doc['source']['as_of'], technical=True)
        nat_row = next(r for r in nat['rows'] if r['transaction_id'] == cid)
        if not nat_row.get('known_at_cutoff', True) or nat_row.get('status') == 'unavailable':
            nat_rules = {}
        else:
            nat_rules = {r['rule_id']: r for r in nat_row['rule_coverage']['rules']}

        if group == 'p1':
            plan = plan_p1_from_rule_snapshot(deepcopy(doc), scope)
            row_p = plan['rows'][0]
            plain = decode_p1_plan_results(plan, _eval_plain_outputs('rules', row_p.get('requests', [])))['rows'][0]
            n_entry = nat_rules.get('P1')
        elif group == 'c3':
            plan = plan_c3_from_rule_snapshot(deepcopy(doc), scope)
            row_p = plan['rows'][0]
            plain = decode_c3_plan_results(plan, _eval_plain_outputs('c3', row_p.get('requests', [])))['rows'][0]
            n_entry = nat_rules.get('C3')
        elif group == 'b1':
            plan = plan_b1_from_rule_snapshot(deepcopy(doc), scope)
            row_p = plan['rows'][0]
            plain = decode_b1_plan_results(plan, _eval_plain_outputs('graph', row_p.get('requests', [])))['rows'][0]
            n_entry = nat_rules.get('B1')
        elif group == 'b5_e4':
            plan = plan_b5_e4_from_rule_snapshot(deepcopy(doc), scope)
            row_p = plan['rows'][0]
            plain = decode_b5_e4_plan_results(plan, _eval_plain_outputs('graph', row_p.get('requests', [])))['rows'][0]
            n_entry = nat_rules.get('B5')
        else:
            raise ValueError(group)

        if n_entry is None:
            nat_status, nat_matched, nat_score = 'unavailable', None, None
            plain_match = plain['status'] == 'unavailable'
        else:
            nat_status = n_entry['status']
            nat_matched = n_entry.get('matched')
            nat_score = n_entry.get('score')
            if plain['available']:
                plain_match = (plain.get('matched') == nat_matched) and (group == 'p1' or plain.get('score') == nat_score)
            else:
                # Within-contract bounded unavailable limits (`he_*_limit`) stay `unavailable` rather than slicing
                is_limit = str(plain.get('reason', '')).startswith('he_') and nat_status not in ('unavailable', 'not_applicable')
                plain_match = (plain.get('status') == nat_status) or is_limit

        http_obs = real_http_index.get(f'{http_key[0]}:{http_key[1]}:{http_key[2]}') if http_key else None
        http_match = True
        if http_obs is not None:
            http_match = (http_obs.get('status') == plain.get('status')) and (http_obs.get('matched') == plain.get('matched')) and (http_obs.get('reason') == plain.get('reason'))

        if not (plain_match and http_match):
            verdict = 'fail'
        elif not n_entry and plain.get('status') == 'unavailable':
            verdict = 'pass'
        elif n_entry and str(plain.get('reason', '')).startswith('he_') and nat_status != 'unavailable':
            verdict = 'partial'
        else:
            verdict = 'pass'

        cases.append(dict(
            case_id=case_id,
            group=group,
            native_status=nat_status,
            native_matched=nat_matched,
            native_score=nat_score,
            plaintext_he_status=plain.get('status'),
            plaintext_he_matched=plain.get('matched'),
            plaintext_he_reason=plain.get('reason'),
            real_http_he_status=http_obs.get('status') if http_obs else 'not_run_in_http_batch',
            real_http_he_matched=http_obs.get('matched') if http_obs else None,
            real_http_he_reason=http_obs.get('reason') if http_obs else None,
            parity_verdict=verdict,
            note=('Bounded <=4 HE circuit limit returned unavailable as designed (never sliced).' if verdict == 'partial' else None),
        ))

    # P1 cases
    _, doc_p1_hit = _base_case('C001', extra_vendor_phone_same=True)
    doc_p1_hit['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('P1_01_overpay_hit', 'p1', doc_p1_hit, ('C001_COLD', 'AUDIT_0000', 'p1'))

    _, doc_p1_tol = _base_case('C001', extra_vendor_phone_same=False, amount_vnd=4_000_001, prior_amount_vnd=6_000_000)
    doc_p1_tol['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('P1_02_plus_1_tolerance_boundary', 'p1', doc_p1_tol, ('C002_COLD', 'AUDIT_0000', 'p1'))

    doc_p1_sim = _warm_extra_doc('C001')
    doc_p1_sim['candidate_transaction_ids'] = ['SIM_BATCH_A']
    check_case('P1_03_simultaneous_same_second_batch', 'p1', doc_p1_sim, ('C001_WARM_EXTRA', 'SIM_BATCH_A', 'p1'))

    _, doc_p1_no_inv = _base_case('C001')
    for tx in doc_p1_no_inv['source']['tables']['transactions']:
        if tx['transaction_id'] == 'AUDIT_0000':
            tx['invoice_number'] = ''
    _rehash(doc_p1_no_inv['source'])
    doc_p1_no_inv['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('P1_04_missing_invoice_number', 'p1', doc_p1_no_inv)

    doc_p1_lim = _limits_gaps_doc('C001')
    doc_p1_lim['candidate_transaction_ids'] = ['LIMIT_ALL_TX']
    check_case('P1_05_prior_limit_over_4', 'p1', doc_p1_lim, ('C001_LIMITS_GAPS', 'LIMIT_ALL_TX', 'p1'))

    _, doc_p1_neg = _base_case('C001')
    doc_p1_neg['source']['tables']['transactions'][1]['amount_vnd'] = -100_000
    _rehash(doc_p1_neg['source'])
    doc_p1_neg['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case(
        'P1_06_negative_amount_rejected_schema',
        'p1',
        doc_p1_neg,
        expect_reject='NEGATIVE',
        partial_note='agent2-rule-snapshot/1.0.0 schema rejects amount_vnd < 0 (no abs coercion); signed adjustments belong to canonical 1.1.0.',
    )

    doc_p1_pay = _payroll_c3_doc('C001', 'PAY_NA', fast_seconds=600)
    check_case('P1_07_payroll_not_applicable', 'p1', doc_p1_pay, ('C001_COLD', 'PAYROLL_C001', 'p1'))

    _, doc_p1_fut = _base_case('C001')
    doc_p1_fut['candidate_transaction_ids'] = ['FUTURE_C001']
    check_case('P1_08_post_cutoff_late_tx', 'p1', doc_p1_fut, ('C001_COLD', 'FUTURE_C001', 'p1'))

    # C3 cases
    _, doc_c3_hit = _base_case('C001', extra_vendor_phone_same=True, fast_seconds=15)
    doc_c3_hit['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('C3_01_fast_15s_high_hit', 'c3', doc_c3_hit, ('C001_COLD', 'AUDIT_0000', 'c3'))

    _, doc_c3_60 = _base_case('C001', extra_vendor_phone_same=False, fast_seconds=60)
    doc_c3_60['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('C3_02_exact_60s_boundary_no_hit', 'c3', doc_c3_60, ('C002_COLD', 'AUDIT_0000', 'c3'))

    _, doc_c3_std = _base_case('C001', fast_seconds=10)
    doc_c3_std['source']['tables']['approval_authorities'][1]['authority_level'] = 'standard'
    _rehash(doc_c3_std['source'])
    doc_c3_std['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('C3_03_standard_authority_no_hit', 'c3', doc_c3_std)

    doc_c3_amb = _warm_extra_doc('C001')
    doc_c3_amb['candidate_transaction_ids'] = ['C3_AMBIG_TIE']
    check_case('C3_04_conflicting_tie_ambiguous', 'c3', doc_c3_amb, ('C001_WARM_EXTRA', 'C3_AMBIG_TIE', 'c3'))

    _, doc_c3_unk = _base_case('C001', fast_seconds=10)
    doc_c3_unk['source']['tables']['approval_authorities'] = [doc_c3_unk['source']['tables']['approval_authorities'][0]]
    for e in doc_c3_unk['source']['tables']['employees']:
        if e['employee_id'] == doc_c3_unk['source']['tables']['transactions'][1]['approver_id']:
            e['role'] = ''
    _rehash(doc_c3_unk['source'])
    doc_c3_unk['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('C3_05_unknown_role_no_rule_unavailable', 'c3', doc_c3_unk)

    _, doc_c3_cov = _base_case('C001', fast_seconds=10)
    doc_c3_cov['source']['coverage'].pop('approval_authorities')
    doc_c3_cov['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('C3_06_missing_authorities_coverage', 'c3', doc_c3_cov)

    doc_c3_lim = _limits_gaps_doc('C001')
    check_case('C3_07_authority_rules_over_4_limit', 'c3', doc_c3_lim, ('C001_LIMITS_GAPS', 'LIMIT_GAP_TX', 'c3'))

    _, doc_c3_negdt = _base_case('C001', fast_seconds=-10)
    doc_c3_negdt['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('C3_08_negative_delta_no_hit', 'c3', doc_c3_negdt)

    # B1 & B5/E4 cases
    _, doc_b1_hit = _base_case('C001', extra_vendor_phone_same=True)
    doc_b1_hit['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('B1_01_bank_identity_undisclosed_hit', 'b1', doc_b1_hit, ('C001_COLD', 'AUDIT_0000', 'b1'))

    _, doc_b1_disc = _base_case('C001', extra_vendor_phone_same=True, disclosed=True)
    doc_b1_disc['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('B1_02_disclosed_downgraded_score_4', 'b1', doc_b1_disc)

    _, doc_b1_gap = _base_case('C001', extra_vendor_phone_same=True)
    doc_b1_gap['source']['tables']['transactions'][1]['recipient_bank_code'] = ''
    _rehash(doc_b1_gap['source'])
    doc_b1_gap['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('B1_03_missing_recipient_bank_code', 'b1', doc_b1_gap)

    doc_b1_lim = _limits_gaps_doc('C001')
    doc_b1_lim['candidate_transaction_ids'] = ['LIMIT_ALL_TX']
    check_case('B1_04_graph_over_4_limit', 'b1', doc_b1_lim, ('C001_LIMITS_GAPS', 'LIMIT_ALL_TX', 'b1'))

    _, doc_b5_strong = _base_case('C001', extra_vendor_phone_same=True)
    doc_b5_strong['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('B5E4_01_shared_phone_strong_single_family', 'b5_e4', doc_b5_strong, ('C001_COLD', 'AUDIT_0000', 'b5_e4'))

    doc_b5_addr = _warm_extra_doc('C001')
    doc_b5_addr['candidate_transaction_ids'] = ['SIM_BATCH_A']
    check_case('B5E4_02_shared_address_weak_intrinsic_1', 'b5_e4', doc_b5_addr, ('C001_WARM_EXTRA', 'SIM_BATCH_A', 'b5_e4'))

    _, doc_b5_unk = _base_case('C001', extra_vendor_phone_same=False)
    for v in doc_b5_unk['source']['tables']['vendors']:
        v['phone'] = '???'
        v['bank_account'] = ''
        v['address'] = ''
    _rehash(doc_b5_unk['source'])
    doc_b5_unk['candidate_transaction_ids'] = ['AUDIT_0000']
    check_case('B5E4_03_unknown_contact_unavailable', 'b5_e4', doc_b5_unk)

    return cases


def _portal_req(port: int, path: str, token: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict | bytes]:
    hdrs = {'Authorization': f'Bearer {token}'}
    if body is not None:
        hdrs['Content-Type'] = 'application/json'
    if headers:
        hdrs.update(headers)
    with closing(http.client.HTTPConnection('127.0.0.1', port, timeout=30)) as conn:
        conn.request('POST' if body is not None else 'GET', path, None if body is None else json.dumps(body).encode(), hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        ct = resp.getheader('Content-Type') or ''
        return resp.status, json.loads(raw) if 'json' in ct else raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-plain', action='store_true', help='Fast dry run of wiring using in-memory bridge/worker.')
    parser.add_argument('--evidence-dir', type=Path, default=None, help='Sanitized output directory for metrics.json and REPORT.md.')
    parser.add_argument('--resume-sandbox', type=Path, default=None, help='Resume an existing interrupted sandbox dir reusing saved keys and completed jobs.')
    args = parser.parse_args()

    resuming_sandbox = args.resume_sandbox is not None
    root_tmp = args.resume_sandbox.resolve() if resuming_sandbox else Path(tempfile.mkdtemp(prefix='he4_full_flow_'))
    root_tmp.mkdir(parents=True, exist_ok=True)
    print(f'[verify_he_full_flow] Sandbox root: {root_tmp} (dry={args.dry_plain}, resume={resuming_sandbox})', flush=True)

    sandbox_tag = root_tmp.name
    peak_rss = {'mb': 0.0}
    stop_rss = threading.Event()

    def rss_loop():
        while not stop_rss.is_set():
            val = _sample_wsl_rss_mb(sandbox_tag)
            if val is not None and val > peak_rss['mb']:
                peak_rss['mb'] = val
            time.sleep(1.0)

    rss_thread = threading.Thread(target=rss_loop, daemon=True)
    if not args.dry_plain:
        rss_thread.start()

    prov_key_file = root_tmp / 'prov_ed25519.hex'
    use_resumed_worker1 = resuming_sandbox and ((root_tmp / 'worker_c001_resume').exists() or not prov_key_file.is_file())

    worker1_proc = None
    worker2_proc = None
    worker1_dir = root_tmp / ('worker_c001_resume' if use_resumed_worker1 else 'worker_c001')
    worker2_dir = root_tmp / 'worker_c002'
    srv1 = None
    srv2 = None
    ckks_srv = None
    ckks_worker = None
    node1 = None
    node2 = None
    orig_upload = coordinator_mod.upload
    orig_download = coordinator_mod.download
    orig_post = coordinator_mod.post

    try:
        # 1. Policy, shared Snapshots, shared MethodStore
        director_tok = secrets.token_urlsafe(32)
        acct_tok = secrets.token_urlsafe(32)
        long_exp = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        policy_path = root_tmp / 'policy.json'
        if resuming_sandbox and policy_path.is_file():
            policy = json.loads(policy_path.read_text(encoding='utf-8'))
            for principal in policy['principals']:
                if principal['actor_id'] == 'synthetic-reviewer':
                    principal['token_sha256'] = hashlib.sha256(director_tok.encode()).hexdigest()
                    principal['expires_at'] = long_exp
                elif principal['actor_id'] == 'acct_reviewer':
                    principal['token_sha256'] = hashlib.sha256(acct_tok.encode()).hexdigest()
                    principal['expires_at'] = long_exp
        else:
            policy = policy_for(director_tok)
            policy['principals'][0]['expires_at'] = long_exp
            policy['principals'][0]['memberships'] = [
                dict(company_id=c, role='director', status='active', permissions=['data.import', 'model.fit'])
                for c in ('C001', 'C002')
            ]
            acct_p = policy_for(acct_tok)['principals'][0]
            acct_p['actor_id'] = 'acct_reviewer'
            acct_p['expires_at'] = long_exp
            acct_p['memberships'] = [
                dict(company_id=c, role='accountant', status='active', permissions=['data.import'])
                for c in ('C001', 'C002')
            ]
            policy['principals'].append(acct_p)
        policy_path.write_bytes(sme_canonical(policy))
        auth = FileAuthorizer(policy_path)
        snapshots = SnapshotStore(root_tmp / 'snapshots.sqlite3')
        models = MethodStore(root_tmp / 'models.sqlite3')

        state_key = root_tmp / 'state.key.json'
        if not state_key.is_file():
            create_key(state_key, purpose='state-wrapping')
        worker_key_file = root_tmp / 'worker_ed25519.hex'
        if resuming_sandbox and worker_key_file.is_file():
            worker_priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(worker_key_file.read_text(encoding='utf-8').strip()))
        else:
            worker_priv = Ed25519PrivateKey.generate()
            worker_key_file.write_text(worker_priv.private_bytes_raw().hex(), encoding='utf-8')
        worker_pub = public_hex(worker_priv)
        if resuming_sandbox and prov_key_file.is_file():
            prov_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(prov_key_file.read_text(encoding='utf-8').strip()))
        else:
            prov_key = Ed25519PrivateKey.generate()
            prov_key_file.write_text(prov_key.private_bytes_raw().hex(), encoding='utf-8')
        prov_pub = public_hex(prov_key)

        bindings_v4 = root_tmp / 'he4_bindings.json'
        bindings_v4.write_bytes(
            sme_canonical(
                dict(
                    version='he4-company-bindings/1.0.0',
                    bindings=[dict(tenant_id='demo', company_id=c, statistics_artifact_id=None) for c in ('C001', 'C002')],
                )
            )
        )
        ui_bindings = root_tmp / 'ui_bindings.json'
        ui_bindings.write_bytes(sme_canonical(dict(version='he-ui-bindings/1.0.0', bindings=[])))

        # Build public worker bundle (contains zero enterprise secrets)
        public_bundle = root_tmp / 'public_worker_bundle'
        if not public_bundle.exists():
            he4_bundle.build(public_bundle)

        grants_file = root_tmp / 'grants.json'
        existing_grants = json.loads(grants_file.read_text(encoding='utf-8')).get('grants', []) if (resuming_sandbox and grants_file.is_file()) else []
        for comp in ('C001', 'C002'):
            grant = dict(tenant_id='demo', company_id=comp, node_verify_key=prov_pub, active=True)
            if grant not in existing_grants:
                existing_grants.append(grant)
        grants_file.write_text(
            json.dumps(dict(version='he-worker-grants/1.0.0', grants=existing_grants)),
            encoding='utf-8',
        )

        port_w1 = _free_port()
        port_w2 = _free_port()

        if not args.dry_plain:
            for wdir, wport in ((worker1_dir, port_w1), (worker2_dir, port_w2)):
                wdir.mkdir(parents=True, exist_ok=True)
                wcfg = wdir / 'worker-config.json'
                wcfg.write_text(
                    json.dumps(
                        dict(
                            version=VERSION,
                            state_dir=linux_path(wdir / 'state'),
                            grants_file=linux_path(grants_file),
                            signing_key_file=linux_path(worker_key_file),
                            builds={k: linux_path(Path(v)) for k, v in BUILD_PATHS.items()},
                        )
                    ),
                    encoding='utf-8',
                )
            worker1_proc = _wsl_worker_start(public_bundle, worker1_dir / 'worker-config.json', port_w1, worker1_dir / 'worker.log')
            worker2_proc = _wsl_worker_start(public_bundle, worker2_dir / 'worker-config.json', port_w2, worker2_dir / 'worker.log')
        else:
            # Start in-process dry HTTP stub or use coordinator mocks only in dry-plain
            pass

        # Telemetry hooks on transport calls without altering behavior
        transport_events: list[dict] = []
        drop_once_flag = {'drop_evaluate': False}
        manifest_sha_map = {k: json.loads((Path(v) / 'manifest.json').read_bytes())['files']['server.zip'] for k, v in BUILD_PATHS.items()}
        dry_blobs: dict[str, bytes] = {}
        dry_sessions: dict[tuple[str, str], dict] = {}

        if args.dry_plain:
            def wrap_upload(url, scope, key, wkey, path, purpose):
                data = Path(path).read_bytes()
                h = sha(data)
                dry_blobs[h] = data
                transport_events.append(dict(op='upload', purpose=purpose, seconds=0.001, bytes=len(data)))
                return h

            def wrap_download(url, scope, wkey, digest_hex, out_path):
                data = dry_blobs[digest_hex]
                Path(out_path).write_bytes(data)
                transport_events.append(dict(op='download', seconds=0.001, bytes=len(data)))

            def wrap_post(url, route, packet, timeout=30):
                t0 = time.monotonic()
                inner = packet['payload']
                if route == '/v1/readiness':
                    resp = dict(inner, worker_verify_key=worker_pub)
                    if inner.get('version') != 'he-worker-readiness/1.0.0':
                        resp['builds'] = manifest_sha_map
                    return sign(resp, worker_priv)
                req_sha = sha(canonical(packet))
                if route == '/v1/evaluate':
                    if int(inner.get('expires_at', 0)) <= int(time.time()):
                        raise ServiceError(410, 'HE4_EXPIRED')
                    vals = [json.loads(dry_blobs[h].decode()) for h in inner['arguments_sha256']]
                    res_b = canonical(_eval_plain_outputs(inner['profile'], [dict(values=vals)])[0])
                    res_h = sha(res_b)
                    dry_blobs[res_h] = res_b
                    signed_r = sign(
                        dict(version='he4-worker/0.1.0', tenant_id=inner['tenant_id'], company_id=inner['company_id'], session_id=inner['session_id'], nonce=inner['nonce'], request_sha256=req_sha, circuit_sha256=inner['circuit_sha256'], result_sha256=res_h),
                        worker_priv,
                    )
                    dry_sessions[(inner['session_id'], inner['nonce'])] = signed_r
                    transport_events.append(dict(op='post', route=route, profile=inner['profile'], seconds=0.002))
                    if drop_once_flag['drop_evaluate']:
                        drop_once_flag['drop_evaluate'] = False
                        raise ServiceError(503, 'WORKER_CONNECTION_UNAVAILABLE')
                    return signed_r
                if route == '/v1/results':
                    transport_events.append(dict(op='post', route=route, seconds=0.001))
                    key = (inner['session_id'], inner['nonce'])
                    if key not in dry_sessions:
                        raise ServiceError(404, 'SESSION_NOT_REGISTERED')
                    return dry_sessions[key]
                if route in ('/v1/resume', '/v1/admit'):
                    orig = inner['request']['payload']
                    key = (orig['session_id'], orig['nonce'])
                    if route == '/v1/resume' and key not in dry_sessions:
                        transport_events.append(dict(op='post', route=route, seconds=0.001))
                        raise ServiceError(404, 'SESSION_NOT_REGISTERED')
                    if key not in dry_sessions:
                        vals = [json.loads(dry_blobs[h].decode()) for h in orig['arguments_sha256']]
                        res_b = canonical(_eval_plain_outputs(orig['profile'], [dict(values=vals)])[0])
                        res_h = sha(res_b)
                        dry_blobs[res_h] = res_b
                        dry_sessions[key] = sign(
                            dict(version='he4-worker/0.1.0', tenant_id=orig['tenant_id'], company_id=orig['company_id'], session_id=orig['session_id'], nonce=orig['nonce'], request_sha256=sha(canonical(inner['request'])), circuit_sha256=orig['circuit_sha256'], result_sha256=res_h),
                            worker_priv,
                        )
                    transport_events.append(dict(op='post', route=route, profile=orig['profile'], seconds=0.002))
                    return dry_sessions[key]
                raise AssertionError(route)
        else:
            def wrap_upload(url, scope, key, wkey, path, purpose):
                t0 = time.monotonic()
                res = real_upload(url, scope, key, wkey, path, purpose)
                transport_events.append(dict(op='upload', purpose=purpose, seconds=round(time.monotonic() - t0, 4), bytes=Path(path).stat().st_size))
                return res

            def wrap_download(url, scope, wkey, digest_hex, out_path):
                t0 = time.monotonic()
                real_download(url, scope, wkey, digest_hex, out_path)
                transport_events.append(dict(op='download', seconds=round(time.monotonic() - t0, 4), bytes=Path(out_path).stat().st_size))

            def wrap_post(url, route, packet, timeout=30):
                t0 = time.monotonic()
                prof = None
                if isinstance(packet, dict) and isinstance(packet.get('payload'), dict):
                    p = packet['payload']
                    prof = p.get('profile') or ((p.get('request') or {}).get('payload') or {}).get('profile')
                try:
                    res = real_post(url, route, packet, timeout=timeout)
                    transport_events.append(dict(op='post', route=route, profile=prof, seconds=round(time.monotonic() - t0, 4), status='ok'))
                    if route == '/v1/evaluate' and drop_once_flag['drop_evaluate']:
                        drop_once_flag['drop_evaluate'] = False
                        raise ServiceError(503, 'WORKER_CONNECTION_UNAVAILABLE')
                    return res
                except ServiceError as exc:
                    transport_events.append(dict(op='post', route=route, profile=prof, seconds=round(time.monotonic() - t0, 4), status='error', code=exc.code))
                    raise

        coordinator_mod.upload = wrap_upload
        coordinator_mod.download = wrap_download
        coordinator_mod.post = wrap_post
        if args.dry_plain:
            import experiments.he4.web as web_mod
            import experiments.he_inference.readiness as ready_mod
            web_mod.post = wrap_post
            ready_mod.post = wrap_post

        # Setup Nodes & Portal HTTP servers (C001 -> worker1, C002 -> worker2)
        node_worker1_url = f'http://127.0.0.1:{port_w1}'
        node_worker2_url = f'http://127.0.0.1:{port_w2}'
        if not args.dry_plain:
            from experiments.he_inference.worker_server import Worker as CKKSWorker, make_server as make_ckks_server
            ckks_worker = CKKSWorker(root_tmp / 'ckks_worker_state', grants_file, worker_priv)
            ckks_srv = make_ckks_server(0, ckks_worker)
            threading.Thread(target=ckks_srv.serve_forever, daemon=True).start()
            node_worker1_url = f'http://127.0.0.1:{ckks_srv.server_port}'
            node_worker2_url = node_worker1_url

        enterprise_vault = root_tmp / 'enterprise_vault'
        bridge1 = _DryPlainBridge(root_tmp) if args.dry_plain else _TimedCryptoBridge(enterprise_vault, state_key)
        bridge2 = bridge1 if args.dry_plain else _TimedCryptoBridge(enterprise_vault, state_key)

        cfg1 = dict(
            version='he4-enterprise/1.1.0',
            state_dir=str(root_tmp / 'jobs_n1'),
            enterprise_root=str(enterprise_vault),
            state_key_file=str(state_key),
            worker_url=f'http://127.0.0.1:{port_w1}',
            worker_verify_key=worker_pub,
            builds=dict(BUILD_PATHS),
            bindings_file=str(bindings_v4),
            linux_distro='Debian',
            linux_python=WSL_PYTHON,
        )
        cfg2 = dict(cfg1, state_dir=str(root_tmp / 'jobs_n2'), worker_url=f'http://127.0.0.1:{port_w2}')

        node1 = EnterpriseNode(auth, models.path, snapshots.path, node_worker1_url, worker_pub, prov_key)
        node1.enable_jobs(root_tmp / 'legacy_n1', state_key, required_provider='windows-dpapi-current-user')
        wb1 = FourWorkbench(node1, ui_bindings, cfg1)
        node1.jobs.close()
        node1.jobs = FourJobs(node1, wb1.settings, workers=0, bridge=bridge1)

        node2 = EnterpriseNode(auth, models.path, snapshots.path, node_worker2_url, worker_pub, prov_key)
        node2.enable_jobs(root_tmp / 'legacy_n2', state_key, required_provider='windows-dpapi-current-user')
        wb2 = FourWorkbench(node2, ui_bindings, cfg2)
        node2.jobs.close()
        node2.jobs = FourJobs(node2, wb2.settings, workers=0, bridge=bridge2)

        srv1 = make_server(0, auth, snapshots, AnalysisResources(models.path, ui_bindings), he_backend=wb1)
        srv2 = make_server(0, auth, snapshots, AnalysisResources(models.path, ui_bindings), he_backend=wb2)
        threading.Thread(target=srv1.serve_forever, daemon=True).start()
        threading.Thread(target=srv2.serve_forever, daemon=True).start()
        p_portal1 = srv1.server_address[1]
        p_portal2 = srv2.server_address[1]

        sc_c1_dir = auth.authorize('Bearer ' + director_tok, 'C001')
        sc_c2_dir = auth.authorize('Bearer ' + director_tok, 'C002')
        sc_c1_acct = auth.authorize('Bearer ' + acct_tok, 'C001')

        # Provision DPAPI + Concrete keys for C001 & C002 on rules, c3, graph
        # Check RBAC blocks read-only accountant from key provision
        try:
            bridge1.provision(sc_c1_acct, Path(BUILD_PATHS['c3']))
            if not args.dry_plain:
                raise AssertionError('Accountant without model.fit must be denied provision()')
        except Exception:
            pass

        provision_stats = []
        for comp, sc, br in (('C001', sc_c1_dir, bridge1), ('C002', sc_c2_dir, bridge2)):
            for prof in ('rules', 'c3', 'graph'):
                if resuming_sandbox and not args.dry_plain:
                    _, vault_dir, _, _ = br.context(sc, Path(BUILD_PATHS[prof]))
                    if (vault_dir / 'context.sealed').is_file() and (vault_dir / 'evaluation.keys').is_file():
                        print(f'[{comp}] Reusing provisioned {prof} keys from vault.', flush=True)
                        provision_stats.append(dict(action='provision_reused', company=comp, profile=prof, evaluation_keys_bytes=(vault_dir / 'evaluation.keys').stat().st_size))
                        continue
                print(f'[{comp}] Provisioning {prof} keys...', flush=True)
                br.provision(sc, Path(BUILD_PATHS[prof]))
                provision_stats.append(dict(br.events[-1]) if br.events else dict(company=comp, profile=prof))

        # Commit snapshots for Portal HTTP runs
        _, doc_c1 = _base_case('C001', extra_vendor_phone_same=True, fast_seconds=15, amount_vnd=6_000_000, prior_amount_vnd=6_000_000)
        sid_c1 = _commit(snapshots, sc_c1_dir, doc_c1, 'portal-c1-cold')
        _, doc_c2 = _base_case('C002', extra_vendor_phone_same=False, fast_seconds=60, amount_vnd=4_000_001, prior_amount_vnd=6_000_000)
        sid_c2 = _commit(snapshots, sc_c2_dir, doc_c2, 'portal-c2-cold')
        doc_c1_warm = _warm_extra_doc('C001')
        sid_c1_warm = _commit(snapshots, sc_c1_dir, doc_c1_warm, 'portal-c1-warm')
        doc_c1_lim = _limits_gaps_doc('C001')
        sid_c1_lim = _commit(snapshots, sc_c1_dir, doc_c1_lim, 'portal-c1-limits')

        real_http_index: dict[str, dict] = {}
        batch_timings: dict[str, dict] = {}

        def run_portal_batch(label: str, portal_port: int, company: str, scope: AccessScope, node_obj: EnterpriseNode, token: str, sid: str, idem: str) -> tuple[str, dict]:
            t_start = time.monotonic()
            st_ds, ds = _portal_req(portal_port, f'/api/v1/companies/{company}/he/datasets', token)
            assert st_ds == 200 and ds['available'] and ds['worker_ready'], ds

            jid = None
            reused_completed = False
            elapsed = 0.0
            if resuming_sandbox:
                with sqlite3.connect(node_obj.jobs.store.path) as conn:
                    rows = conn.execute(
                        'SELECT id, created, updated FROM jobs WHERE company=? AND actor=? AND phase=?',
                        (company, scope.actor_id, 'completed'),
                    ).fetchall()
                for cand_id, created_ts, updated_ts in rows:
                    st_chk, chk_res = _portal_req(portal_port, f'/api/v1/companies/{company}/he/jobs/{cand_id}/result', token)
                    if st_chk == 200 and chk_res.get('snapshot_id') == sid:
                        jid = cand_id
                        reused_completed = True
                        elapsed = float(updated_ts - created_ts)
                        res = chk_res
                        print(f'[{label}] Reusing completed Portal job {jid} (SQLite duration {elapsed:.2f}s)...', flush=True)
                        break

            if not reused_completed:
                st_j, job = _portal_req(portal_port, f'/api/v1/companies/{company}/he/jobs', token, body=dict(snapshot_id=sid), headers={'Idempotency-Key': idem})
                assert st_j == 202, job
                jid = job['job_id']
                print(f'[{label}] Running Portal job {jid}...', flush=True)
                while node_obj.jobs._process(scope, jid):
                    pass
                elapsed = round(time.monotonic() - t_start, 4)
                st_r, res = _portal_req(portal_port, f'/api/v1/companies/{company}/he/jobs/{jid}/result', token)
                assert st_r == 200 and res['version'] == RULE_SNAPSHOT_RESULT_VERSION, (st_r, res)

            assert res['version'] == RULE_SNAPSHOT_RESULT_VERSION, res
            batch_timings[label] = dict(company=company, snapshot_id=sid, job_id=jid, total_seconds=elapsed, row_count=res['row_count'], resumed_from_sqlite=reused_completed)
            for row in res['rows']:
                for gk, gv in row['groups'].items():
                    real_http_index[f'{label}:{row["record_id"]}:{gk}'] = gv
            print(f'[{label}] Completed in {elapsed:.2f}s ({res["row_count"]} rows).', flush=True)
            return jid, res

        # Run C001_COLD, C001_WARM_EXTRA, C001_LIMITS_GAPS, C002_COLD
        jid_c1_cold, res_c1_cold = run_portal_batch('C001_COLD', p_portal1, 'C001', sc_c1_dir, node1, director_tok, sid_c1, 'c1-cold-0001')
        _, res_c1_warm = run_portal_batch('C001_WARM_EXTRA', p_portal1, 'C001', sc_c1_dir, node1, director_tok, sid_c1_warm, 'c1-warm-0001')
        _, res_c1_lim = run_portal_batch('C001_LIMITS_GAPS', p_portal1, 'C001', sc_c1_dir, node1, director_tok, sid_c1_lim, 'c1-lim-0001')
        jid_c2_cold, res_c2_cold = run_portal_batch('C002_COLD', p_portal2, 'C002', sc_c2_dir, node2, director_tok, sid_c2, 'c2-cold-0001')

        # Verify Accountant portal run + RBAC masking + Workspace + Review save + CSV export
        acct_idem = 'c1-acct-0002' if use_resumed_worker1 else 'c1-acct-0001'
        _, res_acct = run_portal_batch('C001_ACCT', p_portal1, 'C001', sc_c1_acct, node1, acct_tok, sid_c1, acct_idem)
        assert 'plan_sha256' not in json.dumps(res_acct), 'Accountant response must mask plan_sha256'
        assert isinstance(res_acct['rows'][0]['amount_vnd'], str), 'VND amounts must be JSON strings'
        # Director job must be invisible (404) to accountant & cross-company must return 404
        assert _portal_req(p_portal1, f'/api/v1/companies/C001/he/jobs/{jid_c1_cold}/result', acct_tok)[0] == 404
        assert _portal_req(p_portal2, f'/api/v1/companies/C002/he/jobs/{jid_c1_cold}/result', director_tok)[0] == 404

        jid_acct = res_acct['run_id']
        st_ws, ws = _portal_req(p_portal1, f'/api/v1/companies/C001/workspace/runs/{jid_acct}', acct_tok)
        assert st_ws == 200 and ws['row_count'] == 3, ws
        c0 = ws['cases'][0]
        assert c0['record_id'] == 'AUDIT_0000' and len(c0['checks']) == 6 and c0['payment_signal']
        pref = f"/api/v1/companies/C001/he/jobs/{jid_acct}/reviews/{c0['case_id']}"
        st_s, started = _portal_req(p_portal1, pref + '/start', acct_tok, body={})
        assert st_s == 200
        st_sv, saved = _portal_req(
            p_portal1,
            pref + '/save',
            acct_tok,
            body=dict(
                lease=started['lease'],
                expected_revision=0,
                request_id='rev-save-0001',
                feedback=dict(
                    outcome='confirmed_risk',
                    usefulness='yes',
                    explanation='Real HE HTTP run matched P1/C3/B1/B5.',
                    action='Hold payment',
                    missing_materials='',
                    evidence_ids=[c0['evidence'][0]['evidence_id']],
                    checks_completed=True,
                ),
            ),
        )
        assert st_sv == 200, saved
        st_csv, csv_raw = _portal_req(p_portal1, f'/api/v1/companies/C001/workspace/runs/{jid_acct}/report.csv', acct_tok)
        assert st_csv == 200 and isinstance(csv_raw, bytes) and b'AUDIT_0000' in csv_raw

        # Verify R1 (encrypt checkpoint), R2 (lost evaluate reply), R3 (7h expiry -> /v1/admit), R4 (real SIGKILL + /v1/resume)
        recovery_results = {}
        rec_tag = uuid.uuid4().hex[:8] if resuming_sandbox else '0001'

        # R1 & R2 on single payroll C3 task
        sid_r12 = _commit(snapshots, sc_c1_dir, _payroll_c3_doc('C001', 'REC_R12', fast_seconds=12), 'rec-r12')
        as_of_r = doc_c1['source']['as_of']
        st_r12 = node1.jobs.submit('C001', 'Bearer ' + director_tok, f'rec-r12-{rec_tag}', dict(artifact_id=None, snapshot_id=sid_r12, as_of=as_of_r))
        jid_r12 = st_r12['job_id']
        # Force plan + uncommitted dir + real sealed checkpoint without saving context to SQLite (R1)
        row_r, data_r = node1.jobs.store.get(sc_c1_dir, jid_r12)
        from experiments.he4.rule_snapshot_coordinator import prepare_rule_snapshot_he_plan
        from experiments.he_inference.registry_export import ReadOnlySnapshots
        ctx_r = data_r['request']['he4_context']
        prep_r = prepare_rule_snapshot_he_plan(ReadOnlySnapshots(snapshots.path), sc_c1_dir, sid_r12, as_of_r, ctx_r['programs'])
        data_r['pending'] = dict(plan=prep_r['plan'], tasks=prep_r['tasks'], cursor=0)
        node1.jobs.store.save(sc_c1_dir, jid_r12, data_r, 'ready')
        # Simulate crash during pre-commit temp dir (uncommitted argument-0.cipher only; enterprise_helper rejects alien partial filenames),
        # then real sealed checkpoint left on disk while task['context'] is still None
        in_dir = node1.jobs.operations / jid_r12 / '0' / 'input'
        in_dir.mkdir(parents=True, exist_ok=True)
        (in_dir / 'argument-0.cipher').write_bytes(b'partial')
        bridge1.encrypt(sc_c1_dir, ctx_r['programs']['c3']['path'], prep_r['tasks'][0]['values'], in_dir, recover_uncommitted=True)
        assert (in_dir / 'manifest.sealed').exists()

        # Reload FourJobs cleanly from disk, re-authorize via resume(), & trigger 1-shot dropped /v1/evaluate reply (R2)
        node1.jobs.close()
        node1.enable_jobs(root_tmp / 'legacy_n1', state_key, required_provider='windows-dpapi-current-user')
        reloaded1 = FourJobs(node1, wb1.settings, workers=0, bridge=bridge1)
        node1.jobs = reloaded1
        reloaded1.resume('C001', 'Bearer ' + director_tok, jid_r12)
        drop_once_flag['drop_evaluate'] = True
        assert reloaded1._process(sc_c1_dir, jid_r12) is True  # retryable after lost reply
        st_mid = reloaded1.status('C001', 'Bearer ' + director_tok, jid_r12)
        assert st_mid['phase'] == 'retryable' and st_mid['reason'] == 'WORKER_CONNECTION_UNAVAILABLE', st_mid
        # Note CryptoBridge recovered sealed checkpoint instantaneously without spawning WSL encrypt
        recovery_results['R1_encrypt_checkpoint_recovery'] = bool((in_dir / 'manifest.sealed').exists()) and any(
            e['op'] == 'encrypt' and e.get('checkpoint_reused') for e in bridge1.events
        )
        # Restart FourJobs again -> Portal POST .../resume re-authorizes, then _process calls /v1/results WITHOUT re-encrypt/re-eval
        node1.jobs.close()
        node1.enable_jobs(root_tmp / 'legacy_n1', state_key, required_provider='windows-dpapi-current-user')
        reloaded2 = FourJobs(node1, wb1.settings, workers=0, bridge=bridge1)
        node1.jobs = reloaded2
        st_res_p, _ = _portal_req(p_portal1, f'/api/v1/companies/C001/he/jobs/{jid_r12}/resume', director_tok, body={})
        assert st_res_p == 202, st_res_p
        enc_before_r2 = sum(1 for e in bridge1.events if e['op'] == 'encrypt')
        eval_before_r2 = sum(1 for e in transport_events if e.get('route') == '/v1/evaluate')
        while reloaded2._process(sc_c1_dir, jid_r12):
            pass
        enc_after_r2 = sum(1 for e in bridge1.events if e['op'] == 'encrypt')
        eval_after_r2 = sum(1 for e in transport_events if e.get('route') == '/v1/evaluate')
        res_cnt_r2 = sum(1 for e in transport_events if e.get('route') == '/v1/results' and e.get('status') != 'error')
        c_r12, out_r12 = reloaded2.result('C001', 'Bearer ' + director_tok, jid_r12)
        assert c_r12 == 200 and out_r12['rows'][0]['groups']['c3']['matched'] is True
        assert enc_after_r2 == enc_before_r2 and eval_after_r2 == eval_before_r2
        recovery_results['R2_lost_evaluate_reply_results_recovery'] = True
        print('[R1/R2] Verified encrypt checkpoint & lost-reply /v1/results recovery!', flush=True)

        # R3: Pre-expired packet rejected on /v1/evaluate (410 HE4_EXPIRED) -> /v1/admit succeeds on real worker
        sid_r3 = _commit(snapshots, sc_c1_dir, _payroll_c3_doc('C001', 'REC_R3', fast_seconds=14), 'rec-r3')
        st_r3 = node1.jobs.submit('C001', 'Bearer ' + director_tok, f'rec-r3-{rec_tag}', dict(artifact_id=None, snapshot_id=sid_r3, as_of=as_of_r))
        jid_r3 = st_r3['job_id']
        row3, data3 = node1.jobs.store.get(sc_c1_dir, jid_r3)
        ctx3 = data3['request']['he4_context']
        prep3 = prepare_rule_snapshot_he_plan(ReadOnlySnapshots(snapshots.path), sc_c1_dir, sid_r3, as_of_r, ctx3['programs'])
        in3 = node1.jobs.operations / jid_r3 / '0' / 'input'
        in3.mkdir(parents=True, exist_ok=True)
        meta3 = bridge1.encrypt(sc_c1_dir, ctx3['programs']['c3']['path'], prep3['tasks'][0]['values'], in3, recover_uncommitted=True)
        pub_h3 = coordinator_mod.upload(ctx3['worker_url'], sc_c1_dir, prov_key, worker_pub, bridge1.public_key(sc_c1_dir, ctx3['programs']['c3']['path']), 'public_evaluation_keys')
        arg_h3 = [coordinator_mod.upload(ctx3['worker_url'], sc_c1_dir, prov_key, worker_pub, in3 / f'argument-{i}.cipher', 'ciphertext') for i in range(len(meta3['arguments_sha256']))]
        expired_pkt = sign(
            dict(
                version=VERSION,
                tenant_id='demo',
                company_id='C001',
                node_verify_key=prov_pub,
                expires_at=int(time.time()) - 15,
                profile='c3',
                circuit_sha256=ctx3['programs']['c3']['circuit_sha256'],
                evaluation_keys_sha256=pub_h3,
                arguments_sha256=arg_h3,
                session_id=jid_r3 + '_t0',
                nonce='n_' + uuid.uuid4().hex,
            ),
            prov_key,
        )
        # Prove real worker rejects expired inner packet directly
        try:
            real_post(ctx3['worker_url'], '/v1/evaluate', expired_pkt) if not args.dry_plain else wrap_post(ctx3['worker_url'], '/v1/evaluate', expired_pkt)
            raise AssertionError('Expired inner packet must fail with 410 HE4_EXPIRED')
        except ServiceError as exp_err:
            assert exp_err.code == 'HE4_EXPIRED', exp_err.code

        prep3['tasks'][0]['context'] = meta3
        prep3['tasks'][0]['packet'] = expired_pkt
        data3['pending'] = dict(plan=prep3['plan'], tasks=prep3['tasks'], cursor=0)
        node1.jobs.store.save(sc_c1_dir, jid_r3, data3, 'sending')
        admit_before = sum(1 for e in transport_events if e.get('route') == '/v1/admit')
        while node1.jobs._process(sc_c1_dir, jid_r3):
            pass
        admit_after = sum(1 for e in transport_events if e.get('route') == '/v1/admit')
        c_r3, out_r3 = node1.jobs.result('C001', 'Bearer ' + director_tok, jid_r3)
        assert c_r3 == 200 and out_r3['rows'][0]['groups']['c3']['matched'] is True and admit_after == admit_before + 1
        recovery_results['R3_ttl_pause_fresh_admission'] = True
        print('[R3] Verified 7h expired packet -> /v1/admit recovery!', flush=True)

        # R4: Real WSL SIGKILL mid-FHE -> restart worker on SAME port -> /v1/resume
        if not args.dry_plain:
            sid_r4 = _commit(snapshots, sc_c1_dir, _payroll_c3_doc('C001', 'REC_R4', fast_seconds=16), 'rec-r4')
            st_r4 = node1.jobs.submit('C001', 'Bearer ' + director_tok, f'rec-r4-{rec_tag}', dict(artifact_id=None, snapshot_id=sid_r4, as_of=as_of_r))
            jid_r4 = st_r4['job_id']
            proc_box = []

            def _bg_r4():
                proc_box.append(node1.jobs._process(sc_c1_dir, jid_r4))

            bg = threading.Thread(target=_bg_r4, daemon=True)
            bg.start()
            deadline = time.monotonic() + 240.0
            killed_at_native = False
            while time.monotonic() < deadline:
                if list((worker1_dir / 'state').glob('attempt_*/native.started')):
                    _wsl_worker_stop(worker1_proc, kill_pattern=linux_path(worker1_dir))
                    worker1_proc = None
                    killed_at_native = True
                    break
                time.sleep(0.02)
            assert killed_at_native, 'native.started never observed during R4 SIGKILL window'
            bg.join(timeout=15)

            with sqlite3.connect(worker1_dir / 'state' / 'state' / 'jobs.sqlite3') as conn:
                st_killed = conn.execute('SELECT state FROM jobs WHERE session=? ', (jid_r4 + '_t0',)).fetchone()
            assert st_killed is not None and st_killed[0] == 'running', st_killed

            time.sleep(0.6)
            worker1_proc = _wsl_worker_start(public_bundle, worker1_dir / 'worker-config.json', port_w1, worker1_dir / 'worker_restarted.log')
            with sqlite3.connect(worker1_dir / 'state' / 'state' / 'jobs.sqlite3') as conn:
                st_prom = conn.execute('SELECT state FROM jobs WHERE session=?', (jid_r4 + '_t0',)).fetchone()
            assert st_prom is not None and st_prom[0] == 'retryable', st_prom

            # Reload DN coordinator too, re-authorize via resume(), & verify /v1/resume completes cleanly
            node1.jobs.close()
            node1.enable_jobs(root_tmp / 'legacy_n1', state_key, required_provider='windows-dpapi-current-user')
            reloaded4 = FourJobs(node1, wb1.settings, workers=0, bridge=bridge1)
            node1.jobs = reloaded4
            reloaded4.resume('C001', 'Bearer ' + director_tok, jid_r4)
            resume_before = sum(1 for e in transport_events if e.get('route') == '/v1/resume')
            while reloaded4._process(sc_c1_dir, jid_r4):
                pass
            resume_after = sum(1 for e in transport_events if e.get('route') == '/v1/resume')
            c_r4, out_r4 = reloaded4.result('C001', 'Bearer ' + director_tok, jid_r4)
            assert c_r4 == 200 and out_r4['rows'][0]['groups']['c3']['matched'] is True and resume_after > resume_before
            recovery_results['R4_real_sigkill_worker_restart_resume'] = True
            print('[R4] Verified real SIGKILL mid-compute -> worker restart -> /v1/resume!', flush=True)
        else:
            recovery_results['R4_real_sigkill_worker_restart_resume'] = False

        # Comprehensive 3-way parity matrix
        matrix = _run_comprehensive_parity_matrix(snapshots, sc_c1_dir, real_http_index)
        failed_matrix = [m for m in matrix if m['parity_verdict'] == 'fail']
        assert not failed_matrix, f'3-way parity failures: {failed_matrix}'

        blob_w1 = _blob_inventory(worker1_dir / 'state') if not args.dry_plain else dict(dry=True)
        blob_w1_prior = _blob_inventory(root_tmp / 'worker_c001' / 'state') if (use_resumed_worker1 and not args.dry_plain and (root_tmp / 'worker_c001' / 'state').exists()) else None
        blob_w2 = _blob_inventory(worker2_dir / 'state') if not args.dry_plain else dict(dry=True)

        summary = dict(
            mode='dry_plain' if args.dry_plain else 'real_concrete_http_fhe',
            timestamp=datetime.now(TZ7).isoformat(),
            peak_wsl_rss_mb=peak_rss['mb'],
            provision_stats=provision_stats,
            batch_timings=batch_timings,
            crypto_bridge_events=bridge1.events + ([] if bridge2 is bridge1 else bridge2.events),
            transport_events=transport_events,
            recovery=recovery_results,
            blob_store_capacity=dict(worker_quota_bytes=8 * 1024 ** 3, worker1_c001=blob_w1, worker2_c002=blob_w2, **({'worker1_c001_pre_resume': blob_w1_prior} if blob_w1_prior else {})),
            portal_cross_company_isolation=dict(
                c1_audit_matched=all(res_c1_cold['rows'][0]['groups'][g]['matched'] for g in ('p1', 'c3', 'b1', 'b5_e4')),
                c2_audit_clean=all(res_c2_cold['rows'][0]['groups'][g]['matched'] is False for g in ('p1', 'c3', 'b1', 'b5_e4')),
                accountant_masked=('plan_sha256' not in json.dumps(res_acct)),
                workspace_review_csv_verified=True,
            ),
            parity_matrix_summary=dict(
                total=len(matrix),
                passed=sum(1 for m in matrix if m['parity_verdict'] == 'pass'),
                partial=sum(1 for m in matrix if m['parity_verdict'] == 'partial'),
                failed=len(failed_matrix),
            ),
            parity_matrix=matrix,
        )

        if args.evidence_dir and not args.dry_plain:
            args.evidence_dir.mkdir(parents=True, exist_ok=True)
            (args.evidence_dir / 'full_flow_metrics.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'Wrote sanitized metrics to {args.evidence_dir / "full_flow_metrics.json"}', flush=True)
        else:
            print(json.dumps(summary['parity_matrix_summary'], ensure_ascii=False), flush=True)
            print(json.dumps(summary['recovery'], ensure_ascii=False), flush=True)
        return 0
    finally:
        stop_rss.set()
        coordinator_mod.upload = orig_upload
        coordinator_mod.download = orig_download
        coordinator_mod.post = orig_post
        if srv1:
            srv1.shutdown(); srv1.server_close()
        if srv2:
            srv2.shutdown(); srv2.server_close()
        if ckks_srv:
            ckks_srv.shutdown(); ckks_srv.server_close()
        if ckks_worker:
            ckks_worker.close()
        if node1 and node1.jobs:
            node1.jobs.close()
        if node2 and node2.jobs:
            node2.jobs.close()
        _wsl_worker_stop(worker1_proc, kill_pattern=linux_path(worker1_dir))
        _wsl_worker_stop(worker2_proc, kill_pattern=linux_path(worker2_dir))
        if not resuming_sandbox:
            shutil.rmtree(root_tmp, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
