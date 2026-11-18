"""Validate exports with each agent's native code and create isolated runtime state.

Supports Agent 1 longitudinal staging, Agent 2 v2 HTTP import/snapshot contract
(`/api/v1/companies/{company_id}/imports/{upload,preview,commit}` matching `portal/agent2_intake.py`),
and Agent 3 e-invoice XML + bank reconciliation pipeline.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import types
import unicodedata
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for rel in ('', 'agent1', 'agent2', 'agent3/agent3_tax_compliance', 'agent4', 'shared/finance_input/src'):
    candidate = str((REPO / rel).resolve())
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def _ensure_unidecode_shim() -> None:
    try:
        import unidecode  # noqa: F401
    except ImportError:
        mod = types.ModuleType('unidecode')

        def _ascii_fold(text: str) -> str:
            norm = unicodedata.normalize('NFD', str(text)).replace('đ', 'd').replace('Đ', 'D')
            return ''.join(ch for ch in norm if unicodedata.category(ch) != 'Mn')

        mod.unidecode = _ascii_fold
        sys.modules['unidecode'] = mod


def a1(folder: Path) -> dict:
    _ensure_unidecode_shim()
    import numpy as np
    import pandas as pd
    from agent1.adaptive.cash_history import weekly_cash
    from agent1.adaptive.data import SCHEMAS, fingerprint, parse_rows, suggested_mapping, validate_dataset

    root = folder / 'runtime/a1'
    root.mkdir(parents=True, exist_ok=True)
    data = {kind: [] for kind in SCHEMAS}
    for kind in SCHEMAS:
        for path in sorted((folder / 'inputs/a1').rglob('*_' + kind + '.csv')):
            raw = pd.read_csv(path, dtype=str, keep_default_na=False)
            rows, errors, _warnings = parse_rows(raw, kind, suggested_mapping(raw.columns, kind), '%Y-%m-%d', 'plain')
            if errors:
                raise ValueError((str(path), errors[:5]))
            data[kind].extend(rows)
        print(f'A1 {kind}: {len(data[kind])}', flush=True)

    inv_count = len(data['invoices'])
    if not (0 < inv_count <= 50000):
        raise AssertionError(f'Expected 1..50000 A1 invoices, got {inv_count}')

    # Verify longitudinal history (>= 24 months) and operating cash components (>= 104 reconciled weeks)
    distinct_months = sorted({r['issue_date'][:7] for r in data['invoices']})
    if len(distinct_months) < 24:
        raise AssertionError(f'Expected >= 24 longitudinal months in A1 invoices, got {len(distinct_months)}')

    validate_dataset(data)

    accounts = sorted({r['account'] for r in data['statements']})
    panel = weekly_cash(data, '2023-01-02', 196, '2026-10-14', accounts)
    valid_weeks = int(np.isfinite(panel).all(axis=1).sum())
    cash_sale_total = float(np.nansum(panel[:, 2]))
    var_cost_total = float(np.nansum(panel[:, 3]))
    if valid_weeks < 104 or cash_sale_total <= 0 or var_cost_total <= 0:
        raise AssertionError(
            f'A1 operating history insufficient: valid_weeks={valid_weeks}, cash_sale={cash_sale_total}, variable_cost={var_cost_total}'
        )

    overdue_outflows = sum(1 for r in data['outflows'] if r['date'] <= '2026-10-14')
    upcoming_outflows = sum(1 for r in data['outflows'] if r['date'] > '2026-10-14')
    if overdue_outflows == 0 or upcoming_outflows == 0:
        raise AssertionError(f'Expected both overdue and upcoming outflows, got overdue={overdue_outflows}, upcoming={upcoming_outflows}')

    version = fingerprint(data)
    counts = {k: len(v) for k, v in data.items()}
    persisted_encrypted = False
    try:
        from cryptography.fernet import Fernet
        from agent1_service.store import Store

        keys = root / 'keys'
        keys.mkdir(exist_ok=True)
        keyfile = keys / 'encryption.key'
        if not keyfile.exists():
            keyfile.write_bytes(Fernet.generate_key())
        store = Store(root / 'state/agent1.db', keyfile.read_bytes())
        store.put_many(
            'MPX10',
            {
                'company_datasets': [dict(id=version, data=data, created_at=datetime.now(timezone.utc).isoformat())],
                'company_dataset_active': [dict(id='active', version=version, counts=counts)],
            },
        )
        store.connection.close()
        persisted_encrypted = True
    except ImportError:
        save(root / 'state/dataset_snapshot_meta.json', dict(version=version, counts=counts))

    summary = dict(
        passed=True,
        counts=counts,
        version=version,
        longitudinal_months=len(distinct_months),
        reconciled_weeks=valid_weeks,
        cash_sale_vnd=int(round(cash_sale_total)),
        variable_cost_vnd=int(round(var_cost_total)),
        overdue_outflows=overdue_outflows,
        upcoming_outflows=upcoming_outflows,
        persisted_encrypted=persisted_encrypted,
    )
    save(root / 'validation.json', summary)
    return summary


def _http_call(method: str, url: str, body=None, headers: dict | None = None, timeout: int = 120):
    req_headers = dict(headers or {})
    payload = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            payload = bytes(body)
        else:
            payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
            req_headers.setdefault('Content-Type', 'application/json; charset=utf-8')
    req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get('Content-Type', '')
            parsed = json.loads(raw.decode('utf-8')) if 'json' in ctype and raw else raw.decode('utf-8', 'replace')
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode('utf-8'))
        except Exception:
            parsed = {'error': raw.decode('utf-8', 'replace')}
        return exc.code, parsed


def _make_v2_snapshot_server(authorizer, snapshot_store):
    """Create Agent 2 v2 HTTP server supporting /api/v1/companies/{id}/imports/{upload,preview,commit}."""
    try:
        from sme_fraud.review_server import make_server

        return make_server(0, authorizer=authorizer, snapshot_store=snapshot_store)
    except ImportError:
        from sme_fraud.snapshot_api import handle_snapshots

        class V2SnapshotHandler(BaseHTTPRequestHandler):
            def respond(self, code, value, mime='application/json; charset=utf-8'):
                body = (
                    value
                    if isinstance(value, bytes)
                    else (json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)).encode('utf-8')
                )
                self.send_response(code)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not handle_snapshots(self, authorizer, snapshot_store, 'GET'):
                    self.respond(410, {'error': 'Deprecated v1 endpoint removed.'})

            def do_POST(self):
                if not handle_snapshots(self, authorizer, snapshot_store, 'POST'):
                    self.respond(410, {'error': 'Deprecated v1 endpoint removed.'})

            def do_PUT(self):
                if not handle_snapshots(self, authorizer, snapshot_store, 'PUT'):
                    self.respond(410, {'error': 'Deprecated v1 endpoint removed.'})

            def log_message(self, *_args):
                pass

        return ThreadingHTTPServer(('127.0.0.1', 0), V2SnapshotHandler)


def _ensure_scipy_stats_shim() -> None:
    try:
        import scipy.stats  # noqa: F401
    except ImportError:
        import math
        from collections import namedtuple

        PowerDivResult = namedtuple('Power_divergenceResult', ['statistic', 'pvalue'])

        def _chisquare(f_obs, f_exp=None):
            obs = [float(x) for x in f_obs]
            exp = [float(x) for x in f_exp] if f_exp is not None else [sum(obs) / len(obs)] * len(obs)
            stat = sum((o - e) ** 2 / e for o, e in zip(obs, exp) if e > 0)
            df = max(1, len(obs) - 1)
            # Wilson-Hilferty normal approximation to upper-tail chi-square p-value
            z = ((stat / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df)) if stat > 0 else -10.0
            pval = max(0.0, min(1.0, 0.5 * math.erfc(z / math.sqrt(2.0))))
            return PowerDivResult(stat, pval)

        scipy_mod = types.ModuleType('scipy')
        stats_mod = types.ModuleType('scipy.stats')
        stats_mod.chisquare = _chisquare
        scipy_mod.stats = stats_mod
        sys.modules.setdefault('scipy', scipy_mod)
        sys.modules['scipy.stats'] = stats_mod


def a2(folder: Path, *, agent2_url: str | None = None, bearer_token: str | None = None) -> dict:
    """Stage Agent 2 via the v2 /api/v1/companies/{company_id}/imports/{upload,preview,commit} contract."""
    _ensure_scipy_stats_shim()
    from portal import agent2_intake
    from sme_fraud.auth import FileAuthorizer
    from sme_fraud.import_files import canonical
    from sme_fraud.rule_evaluation import _evaluate
    from sme_fraud.rule_sources import _resolve
    from sme_fraud.snapshot_features import COLUMNS, build_from_snapshot
    from sme_fraud.snapshots import SnapshotStore

    root = folder / 'runtime/a2'
    if root.exists():
        for old_db in root.glob('*.sqlite3*'):
            old_db.unlink()
    root.mkdir(parents=True, exist_ok=True)

    bundle_path = folder / 'inputs/a2/canonical_bundle.json'
    chunk_path = folder / 'inputs/a2/chunks/transactions_0001.csv'
    if not bundle_path.is_file():
        raise FileNotFoundError(f'Missing Agent 2 canonical 1.1.0 bundle: {bundle_path}')
    if not chunk_path.is_file():
        raise FileNotFoundError(f'Missing Agent 2 tabular CSV chunk: {chunk_path}')

    company_name = 'Công ty Cổ phần Phân phối và Dịch vụ Minh Phát — MÔ PHỎNG'
    companies_csv = folder / 'inputs/a2/companies.csv'
    if companies_csv.is_file():
        with companies_csv.open(encoding='utf-8-sig', newline='') as f:
            first_co = next(csv.DictReader(f), None)
            if first_co and first_co.get('name'):
                company_name = first_co['name']

    snap_store = SnapshotStore(root / 'snapshots-v2.sqlite3')
    token = bearer_token or secrets.token_urlsafe(32)
    policy_path = root / 'auth-policy.json'
    policy = {
        'policy_version': '1.0.0',
        'principals': [
            {
                'actor_id': 'pipeline-stager',
                'tenant_id': 'demo',
                'token_sha256': hashlib.sha256(token.encode('utf-8')).hexdigest(),
                'status': 'active',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                'memberships': [
                    {
                        'company_id': 'MPX10',
                        'role': 'director',
                        'status': 'active',
                        'permissions': ['data.import', 'evidence.verify', 'model.fit'],
                    }
                ],
            }
        ],
    }
    policy_path.write_bytes(canonical(policy))
    auth = FileAuthorizer(policy_path)

    server = None
    thread = None
    if not agent2_url:
        server = _make_v2_snapshot_server(auth, snap_store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_origin = f'http://127.0.0.1:{server.server_port}'
    else:
        base_origin = agent2_url.rstrip('/')

    try:
        url_fn = lambda p: base_origin + p  # noqa: E731

        # 1. Stage Canonical 1.1.0 JSON bundle through /imports/upload -> /preview -> /commit
        raw_json = bundle_path.read_bytes()
        pending_json = agent2_intake.preview(
            _http_call, url_fn, token, 'demo', 'MPX10', company_name, 'canonical_bundle.json', raw_json
        )
        snap_json = agent2_intake.commit(_http_call, url_fn, token, 'MPX10', pending_json)
        snapshot_id = snap_json['snapshot_id']
        print(f'A2 v2 JSON committed: snapshot_id={snapshot_id}', flush=True)

        # 2. Verify Tabular CSV intake compatibility through /imports/upload -> /preview -> /commit
        raw_csv_lines = chunk_path.read_text(encoding='utf-8-sig').splitlines(keepends=True)
        bounded_csv = ''.join(raw_csv_lines[:501]).encode('utf-8')
        pending_csv = agent2_intake.preview(
            _http_call, url_fn, token, 'demo', 'MPX10', company_name, 'transactions_0001.csv', bounded_csv
        )
        snap_csv = agent2_intake.commit(_http_call, url_fn, token, 'MPX10', pending_csv)
        csv_snapshot_id = snap_csv['snapshot_id']
        print(f'A2 v2 CSV committed: snapshot_id={csv_snapshot_id}', flush=True)

        # 3. Verify GET /api/v1/companies/MPX10/snapshots/{snapshot_id} round-trip
        st_get, snap_meta = _http_call(
            'GET', url_fn(f'/api/v1/companies/MPX10/snapshots/{snapshot_id}'), None, {'Authorization': f'Bearer {token}'}
        )
        if st_get != 200 or snap_meta.get('snapshot_id') != snapshot_id:
            raise RuntimeError(f'Snapshot GET verification failed: {st_get} {snap_meta}')
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)

    # 4. Run point-in-time feature extraction + canonical rule evaluation on the committed snapshot
    if not agent2_url:
        header = 'Bearer ' + token
        scope = auth.authorize(header, 'MPX10')
        recheck = lambda: auth.authorize(header, 'MPX10')  # noqa: E731
        as_of_ts = '2026-10-14T23:59:59+07:00'
        frame = build_from_snapshot(snap_store, scope, snapshot_id, as_of_ts, recheck)
        bundle_doc = json.loads(snap_store.get_snapshot(scope, snapshot_id, recheck, data=True).decode('utf-8'))
        private_src, public_src = _resolve(bundle_doc, frame, scope)

        rule_hits: dict[str, list[str]] = {}
        for meta in frame['rows']:
            key = (meta['record_id'], meta['revision'])
            ev = _evaluate(private_src[key], public_src[key], scope, meta)
            for r in ev['rules']:
                if r['status'] == 'evaluated_hit':
                    rule_hits.setdefault(r['rule_id'], []).append(meta['record_id'])

        col_idx = {name: i for i, name in enumerate(COLUMNS)}
        feat_matrix = frame['features']
        signal_counts = {
            'self_approval_rows': sum(1 for row in feat_matrix if row[col_idx['creator_equals_approver']] == 1.0),
            'round_million_rows': sum(1 for row in feat_matrix if row[col_idx['round_million']] == 1.0),
            'weekend_rows': sum(1 for row in feat_matrix if row[col_idx['event_weekend']] == 1.0),
            'employee_bank_overlap_rows': sum(
                1 for row in feat_matrix if row[col_idx['employee_bank_overlap_observed']] == 1.0
            ),
            'imbalanced_journal_rows': sum(
                1
                for row in feat_matrix
                if row[col_idx['journal_imbalance_abs_ratio']] is not None and row[col_idx['journal_imbalance_abs_ratio']] > 0
            ),
        }
        if 'P1' not in rule_hits or 'DUP-PAY' not in rule_hits.get('P1', []):
            raise AssertionError(f'Expected canonical P1 hit on DUP-PAY, got {rule_hits}')
        if 'E3' not in rule_hits:
            raise AssertionError(f'Expected canonical E3 fuzzy vendor hit, got {rule_hits}')
        if signal_counts['self_approval_rows'] == 0 or signal_counts['employee_bank_overlap_rows'] == 0:
            raise AssertionError(f'Expected non-zero self-approval & employee-bank overlap features, got {signal_counts}')
    else:
        rule_hits = {}
        signal_counts = {}

    summary = dict(
        passed=True,
        contract_version='1.1.0',
        snapshot_id=snapshot_id,
        csv_snapshot_id=csv_snapshot_id,
        import_id=pending_json['import_id'],
        transactions=pending_json['summary']['rows'],
        csv_bank_transactions=pending_csv['summary']['rows'],
        canonical_rule_hits=rule_hits,
        feature_signal_counts=signal_counts,
    )
    save(root / 'preview.json', pending_json['preview'])
    save(root / 'validation.json', summary)
    return summary


def _find_a3_python() -> str | None:
    try:
        import cryptography  # noqa: F401
        import lxml  # noqa: F401

        return sys.executable
    except ImportError:
        candidates = [
            REPO / 'agent3/agent3_tax_compliance/.venv/Scripts/python.exe',
            REPO / 'agent3/.venv/Scripts/python.exe',
            Path(r'C:\ProgramData\miniconda3\python.exe'),
            Path(r'C:\ProgramData\miniconda3\envs\melo\python.exe'),
        ]
        for cand in candidates:
            if cand.is_file():
                probe = subprocess.run(
                    [str(cand), '-c', 'import lxml, cryptography'],
                    capture_output=True,
                    text=True,
                )
                if probe.returncode == 0:
                    return str(cand)
        return None


def a3(folder: Path) -> dict:
    root = folder / 'runtime/a3'
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    pack = json.loads((folder / 'inputs/a3/pack.json').read_text(encoding='utf-8'))
    ws = root / pack['profile']['tax_code']
    ws.mkdir(exist_ok=True)
    shutil.copy2(folder / 'inputs/a3/pack.json', ws / 'pack.json')
    save(ws / 'labels.json', dict(as_of='2026-10-14'))

    expected_xml = {'purchase': 0, 'sales': 0}
    for path in sorted((folder / 'inputs/a3').rglob('*.zip')):
        role = path.stem.split('_')[0]
        dest = ws / 'invoices' / role
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if Path(name).name != name or not name.endswith('.xml'):
                    raise ValueError(name)
                (dest / name).write_bytes(z.read(name))
                if role in expected_xml:
                    expected_xml[role] += 1

    (ws / 'bank').mkdir(exist_ok=True)
    for path in sorted((folder / 'inputs/a3').rglob('bank.csv')):
        shutil.copy2(path, ws / 'bank' / (path.parent.name + '.csv'))

    rows = []
    for path in sorted((folder / 'inputs/a3').rglob('purchase_portal.csv')):
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows.extend(csv.DictReader(f))
    if rows:
        (ws / 'portal').mkdir(exist_ok=True)
        with (ws / 'portal/purchase_list.csv').open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    py_a3 = _find_a3_python()
    if py_a3 and Path(py_a3).resolve() != Path(sys.executable).resolve():
        print(f'A3 staged; invoking native pipeline via {py_a3}', flush=True)
        env = dict(os.environ, PYTHONUTF8='1', PYTHONPATH=str(REPO / 'agent3/agent3_tax_compliance'))
        snippet = (
            'import json, sys; from datetime import date; from pathlib import Path; '
            'from src.assistant import pipeline, report; '
            'ws = Path(sys.argv[1]); rep = pipeline.run(ws, as_of=date(2026, 10, 14)); '
            'report.write(rep, ws / "out"); '
            'by_code = {}; '
            '[by_code.__setitem__(it.code, by_code.get(it.code, 0) + 1) for it in rep.items]; '
            'matched = sum(1 for m in rep.matches if m.status == "MATCHED"); '
            'words_err = sum(1 for i in rep.invoices if "XML_CHECK_WORDS" in i.guard_errors); '
            'arith_err = sum(1 for i in rep.invoices if any("ARITH" in e for e in i.guard_errors)); '
            'out = dict(passed=not rep.meta.get("unreadable") and words_err == 0 and arith_err == 0, '
            'meta=rep.meta, matched_payments=matched, risk_by_code=by_code, '
            'words_errors=words_err, arith_errors=arith_err, policy_flags=len(rep.policy_flags)); '
            '(ws.parent / "validation.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")'
        )
        subprocess.run([py_a3, '-c', snippet, str(ws)], cwd=REPO, env=env, check=True)
        summary = json.loads((root / 'validation.json').read_text(encoding='utf-8'))
    else:
        print('A3 staged; running native pipeline in-process', flush=True)
        from src.assistant import pipeline, report

        rep = pipeline.run(ws, as_of=date(2026, 10, 14))
        report.write(rep, ws / 'out')
        by_code: dict[str, int] = {}
        for it in rep.items:
            by_code[it.code] = by_code.get(it.code, 0) + 1
        matched = sum(1 for m in rep.matches if m.status == 'MATCHED')
        words_err = sum(1 for i in rep.invoices if 'XML_CHECK_WORDS' in i.guard_errors)
        arith_err = sum(1 for i in rep.invoices if any('ARITH' in e for e in i.guard_errors))
        summary = dict(
            passed=not rep.meta.get('unreadable') and words_err == 0 and arith_err == 0,
            meta=rep.meta,
            matched_payments=matched,
            risk_by_code=by_code,
            words_errors=words_err,
            arith_errors=arith_err,
            policy_flags=len(rep.policy_flags),
        )
        save(root / 'validation.json', summary)

    counts = summary['meta']['counts']
    assert counts['purchase_invoices'] == expected_xml['purchase'] and expected_xml['purchase'] > 0
    assert counts['sales_invoices'] == expected_xml['sales'] and expected_xml['sales'] > 0
    assert summary['words_errors'] == 0, f'Expected 0 XML_CHECK_WORDS errors, got {summary["words_errors"]}'
    assert summary['arith_errors'] == 0, f'Expected 0 XML arithmetic errors, got {summary["arith_errors"]}'
    assert summary['matched_payments'] > 0, 'Expected > 0 bank-matched AP invoices in A3'
    assert summary['risk_by_code'].get('R02_SAME_DAY_CUMULATIVE', 0) > 0, (
        f'Expected R02_SAME_DAY_CUMULATIVE showcase hit, got {summary["risk_by_code"]}'
    )
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('agent', choices=['a1', 'a2', 'a3', 'all'])
    p.add_argument('--agent2-url', default=None)
    p.add_argument('--token', default=None)
    args = p.parse_args()
    folder = args.folder.resolve()
    targets = ('a1', 'a2', 'a3') if args.agent == 'all' else (args.agent,)
    for target in targets:
        if target == 'a2':
            a2(folder, agent2_url=args.agent2_url, bearer_token=args.token)
        else:
            globals()[target](folder)


if __name__ == '__main__':
    main()
