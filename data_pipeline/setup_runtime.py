"""Synchronize datasets, Portal configuration, company profile, and Agent 1-4 runtime states.

Usage:
  python data_pipeline/setup_runtime.py                # Auto: use full dataset if present, else unpack LFS warehouse, sync all configs & Agent 2 models
  python data_pipeline/setup_runtime.py --mode full    # Full: generate complete 4-year MPX10 dataset + exports + demo inputs, then sync all configs & models
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'portal' / 'workspace'
DATASETS = WORK / 'datasets'


def find_venv_python(agent_name: str) -> str:
    for base in (ROOT / agent_name, ROOT / 'agent3' / 'agent3_tax_compliance' if agent_name == 'agent3' else ROOT / agent_name):
        for rel in (Path('.venv/Scripts/python.exe'), Path('.venv/bin/python')):
            candidate = base / rel
            if candidate.exists():
                return str(candidate)
    if agent_name == 'agent4':
        for fallback in (Path.home() / '.venvs/maf-agent4/Scripts/python.exe', Path.home() / '.venvs/maf-agent4/bin/python'):
            if fallback.exists():
                return str(fallback)
    return sys.executable


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.25)
        return s.connect_ex(('127.0.0.1', port)) == 0


def unpack_zlib_warehouse(zlib_path: Path, out_duckdb: Path) -> None:
    print(f'[data] Giải nén kho DuckDB từ {zlib_path.relative_to(ROOT)} ...', flush=True)
    out_duckdb.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_duckdb.with_suffix('.duckdb.tmp')
    decompressor = zlib.decompressobj()
    with zlib_path.open('rb') as src, tmp.open('wb') as dst:
        while True:
            chunk = src.read(4 * 1024 * 1024)
            if not chunk:
                break
            dst.write(decompressor.decompress(chunk))
        dst.write(decompressor.flush())
    tmp.replace(out_duckdb)
    print(f'[data] Đã giải nén kho DuckDB: {out_duckdb.relative_to(ROOT)} ({out_duckdb.stat().st_size // (1024 * 1024)} MB)', flush=True)


def ensure_dataset(mode: str) -> Path:
    py4 = find_venv_python('agent4')
    full_dir = DATASETS / 'enterprise-x10-v3-full'
    cand_dir = DATASETS / 'enterprise-x10-v3-candidate02'
    smoke_dir = DATASETS / 'enterprise-x10-v3-smoke'

    if mode == 'full':
        target = full_dir
        if (target / 'warehouse.duckdb').is_file():
            print(f'[data] Đã có sẵn kho đầy đủ: {target.relative_to(ROOT)}', flush=True)
        else:
            print(f'[data] Đang sinh bộ dữ liệu Minh Phát MPX10 đầy đủ tại {target.relative_to(ROOT)} ...', flush=True)
            env = dict(os.environ, PYTHONUTF8='1')
            subprocess.run([py4, str(ROOT / 'data_pipeline/enterprise.py'), '--out', str(target)], cwd=ROOT, env=env, check=True)
            subprocess.run([py4, str(ROOT / 'data_pipeline/export.py'), str(target)], cwd=ROOT, env=env, check=True)
            subprocess.run([py4, str(ROOT / 'data_pipeline/validate.py'), str(target)], cwd=ROOT, env=env, check=True)
    else:
        if (full_dir / 'warehouse.duckdb').is_file():
            target = full_dir
        elif (cand_dir / 'warehouse.duckdb').is_file():
            target = cand_dir
        elif (cand_dir / 'warehouse.duckdb.zlib').is_file() and (cand_dir / 'warehouse.duckdb.zlib').stat().st_size > 1024:
            # Verify it is real binary zlib data, not an unpulled Git LFS pointer
            head = (cand_dir / 'warehouse.duckdb.zlib').read_bytes()[:64]
            if not head.startswith(b'version https://git-lfs.github.com'):
                unpack_zlib_warehouse(cand_dir / 'warehouse.duckdb.zlib', cand_dir / 'warehouse.duckdb')
                target = cand_dir
            elif (smoke_dir / 'warehouse.duckdb').is_file():
                target = smoke_dir
            else:
                target = smoke_dir
                print(f'[data] Sinh nhanh kho dữ liệu mẫu (--smoke) tại {target.relative_to(ROOT)} ...', flush=True)
                env = dict(os.environ, PYTHONUTF8='1')
                subprocess.run([py4, str(ROOT / 'data_pipeline/enterprise.py'), '--smoke', '--out', str(target)], cwd=ROOT, env=env, check=True)
                subprocess.run([py4, str(ROOT / 'data_pipeline/export.py'), str(target)], cwd=ROOT, env=env, check=True)
                subprocess.run([py4, str(ROOT / 'data_pipeline/validate.py'), str(target)], cwd=ROOT, env=env, check=True)
        elif (smoke_dir / 'warehouse.duckdb').is_file():
            target = smoke_dir
        else:
            target = smoke_dir
            print(f'[data] Sinh nhanh kho dữ liệu mẫu (--smoke) tại {target.relative_to(ROOT)} ...', flush=True)
            env = dict(os.environ, PYTHONUTF8='1')
            subprocess.run([py4, str(ROOT / 'data_pipeline/enterprise.py'), '--smoke', '--out', str(target)], cwd=ROOT, env=env, check=True)
            subprocess.run([py4, str(ROOT / 'data_pipeline/export.py'), str(target)], cwd=ROOT, env=env, check=True)
            subprocess.run([py4, str(ROOT / 'data_pipeline/validate.py'), str(target)], cwd=ROOT, env=env, check=True)

    # Ensure demo intake bundle exists from whichever dataset has exported inputs
    demo_bundle = WORK / 'mpx10-demo-input-full'
    if not (demo_bundle / '01_invoices.csv').is_file():
        for src_dir in (target, full_dir, smoke_dir):
            if (src_dir / 'inputs/a1').is_dir() and (src_dir / 'inputs/a2').is_dir() and (src_dir / 'inputs/a3').is_dir():
                if demo_bundle.exists():
                    for f in demo_bundle.iterdir():
                        if f.is_file():
                            f.unlink()
                    demo_bundle.rmdir()
                subprocess.run(
                    [py4, str(ROOT / 'data_pipeline/demo_inputs.py'), str(src_dir), str(demo_bundle)],
                    cwd=ROOT, env=dict(os.environ, PYTHONUTF8='1'), check=False,
                )
                break

    return target / 'warehouse.duckdb'


def sync_portal_files(warehouse_db: Path) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    cfg_example = json.loads((ROOT / 'portal/config.example.json').read_text(encoding='utf-8'))
    cfg_local_path = ROOT / 'portal/config.local.json'
    cfg = json.loads(cfg_local_path.read_text(encoding='utf-8')) if cfg_local_path.is_file() else dict(cfg_example)

    cfg.setdefault('port', 8800)
    cfg.setdefault('workspace', 'portal/workspace')
    if cfg.get('demo_company') is None:
        cfg['demo_company'] = {'code': 'MPX10', 'tax_code': '0999999905'}

    agents = cfg.setdefault('agents', {})
    for aid, default_agent_cfg in cfg_example.get('agents', {}).items():
        merged = dict(default_agent_cfg)
        merged.update(agents.get(aid, {}))
        # Remove machine-specific python overrides if standard .venv exists
        if 'python' in merged and (ROOT / aid / '.venv').exists():
            merged.pop('python', None)
        agents[aid] = merged

    rel_db = warehouse_db.resolve().relative_to(ROOT.resolve()).as_posix()
    a4_env = dict(agents.get('agent4', {}).get('env') or {})
    a4_env['AGENT4_DB_PATH'] = rel_db
    agents['agent4']['env'] = a4_env

    cfg_local_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # Default company profile (MPX10) if not yet configured
    company_path = WORK / 'company.json'
    if not company_path.is_file():
        company_data = {
            'code': 'MPX10',
            'legal_name': 'Công ty Cổ phần Phân phối và Dịch vụ Minh Phát — MÔ PHỎNG',
            'tax_code': '0999999905',
            'registered_address': 'Số 195 Điện Biên Phủ, Quận Bình Thạnh, TP. Hồ Chí Minh (Mô phỏng)',
            'industry': 'Phân phối thiết bị công nghệ và dịch vụ kỹ thuật',
            'vat_method': 'DEDUCTION',
            'filing_period': 'MONTH',
            'fiscal_year_end_month': 12,
            'date_format': 'iso',
            'number_format': 'plain',
            'agent2_company': '',
        }
        company_path.write_text(json.dumps(company_data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    else:
        company_data = json.loads(company_path.read_text(encoding='utf-8'))

    # Sync Agent 1 profile file
    code = str(company_data.get('code') or 'MPX10').strip().upper()
    a1_prof_dir = WORK / 'agent1_profiles'
    a1_prof_dir.mkdir(parents=True, exist_ok=True)
    (a1_prof_dir / f'{code}.json').write_text(
        json.dumps({
            'code': code,
            'date_format': company_data.get('date_format', 'iso'),
            'number_format': company_data.get('number_format', 'plain'),
        }, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    # Sync Agent 2 operator access memberships (preserves existing memberships + adds standard demo companies)
    access_path = WORK / 'agent2_access.json'
    default_companies = ['MPX10', 'C001', 'C002', 'SME', 'KT', 'DAIPHAT', 'SAOVIET']
    if code and code not in default_companies:
        default_companies.insert(0, code)
    existing_memberships = []
    tenant_id = 'demo'
    actor_id = 'portal-workspace'
    if access_path.is_file():
        try:
            old_access = json.loads(access_path.read_text(encoding='utf-8'))
            tenant_id = old_access.get('tenant_id', 'demo')
            actor_id = old_access.get('actor_id', 'portal-workspace')
            existing_memberships = list(old_access.get('memberships') or [])
        except Exception:
            existing_memberships = []
    seen = {m.get('company_id') for m in existing_memberships if isinstance(m, dict)}
    for cid in default_companies:
        if cid not in seen:
            existing_memberships.append({
                'company_id': cid,
                'role': 'director',
                'status': 'active',
                'permissions': ['data.import', 'evidence.verify', 'model.fit'],
            })
            seen.add(cid)
    access_doc = {
        'version': 'portal-agent2-access/1.0.0',
        'actor_id': actor_id,
        'tenant_id': tenant_id,
        'status': 'active',
        'memberships': existing_memberships,
    }
    access_path.write_text(json.dumps(access_doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # Sync Agent 3 simulated workspace pack.json for MPX10 (0999999905)
    a3_ws = WORK / 'agent3/workspaces/0999999905'
    a3_ws.mkdir(parents=True, exist_ok=True)
    pack_path = a3_ws / 'pack.json'
    if not pack_path.is_file():
        pack_doc = {
            'pack_version': 1,
            'simulated': True,
            'profile': {
                'tax_code': '0999999905',
                'legal_name': company_data.get('legal_name') if code == 'MPX10' else 'Công ty Cổ phần Phân phối và Dịch vụ Minh Phát — MÔ PHỎNG',
                'registered_address': company_data.get('registered_address') or 'Địa chỉ mô phỏng',
                'industry': [x.strip() for x in str(company_data.get('industry') or 'Phân phối thiết bị').split(';') if x.strip()],
                'vat_method': company_data.get('vat_method', 'DEDUCTION'),
                'filing_period': company_data.get('filing_period', 'MONTH'),
                'fiscal_year_end_month': int(company_data.get('fiscal_year_end_month', 12)),
            },
            'policies': [],
            'thresholds': {},
            'bank_formats': [],
            'reference_lists': [],
            'ai_categories': [],
            'days_off': [],
        }
        pack_path.write_text(json.dumps(pack_doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


AGENT2_PROVISION_SNIPPET = r"""
import copy, hashlib, json, secrets, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
AGENT2 = ROOT / 'agent2'
sys.path.insert(0, str(AGENT2))
sys.path.insert(0, str(AGENT2 / 'scripts'))
sys.path.insert(0, str(ROOT / 'shared' / 'finance_input' / 'src'))

from demo_method_scores import canonical_source
from sme_fraud.analysis_resources import VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.snapshots import SnapshotStore

run_dir = AGENT2 / '.runtime' / 'platform'
run_dir.mkdir(parents=True, exist_ok=True)
snap_path = run_dir / 'snapshots-v2.sqlite3'
model_path = run_dir / 'models-v2.sqlite3'
bindings_path = run_dir / 'analysis-bindings.json'

target_companies = [('MPX10', 'isolation_forest', 3), ('C001', 'isolation_forest', 1), ('C002', 'ecod', 2)]

if model_path.is_file() and bindings_path.is_file():
    try:
        b = json.loads(bindings_path.read_text('utf-8'))
        bound_ids = {row['company_id'] for row in b.get('bindings', []) if row.get('statistics_artifact_id') and row.get('ml_artifacts')}
        if {'MPX10', 'C001', 'C002'} <= bound_ids:
            sys.exit(0)
    except Exception:
        pass

tok = secrets.token_urlsafe(32)
with tempfile.TemporaryDirectory() as tmp:
    policy_path = Path(tmp) / 'policy.json'
    policy = {
        'policy_version': '1.0.0',
        'principals': [{
            'actor_id': 'runtime-provisioner',
            'tenant_id': 'demo',
            'token_sha256': hashlib.sha256(tok.encode()).hexdigest(),
            'status': 'active',
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            'memberships': [
                {'company_id': cid, 'role': 'director', 'status': 'active', 'permissions': ['data.import', 'model.fit', 'evidence.verify']}
                for cid, _, _ in target_companies
            ],
        }],
    }
    policy_path.write_bytes(canonical(policy))
    auth = FileAuthorizer(policy_path)
    snapshots = SnapshotStore(snap_path)
    models = MethodStore(model_path)
    header = 'Bearer ' + tok
    bindings = []

    mpx10_bundle_candidates = [
        ROOT / 'portal/workspace/datasets/enterprise-x10-v3-full/inputs/a2/canonical_bundle.json',
        ROOT / 'portal/workspace/datasets/enterprise-x10-v3-candidate02/inputs/a2/canonical_bundle.json',
        ROOT / 'portal/workspace/datasets/enterprise-x10-v3-smoke/inputs/a2/canonical_bundle.json',
        ROOT / 'portal/workspace/mpx10-demo-input-full/03_agent2_bundle.json',
    ]
    mpx10_bundle_file = next((p for p in mpx10_bundle_candidates if p.is_file()), None)

    for cid, ml_method, scale in target_companies:
        if cid == 'MPX10' and mpx10_bundle_file is not None:
            src = json.loads(mpx10_bundle_file.read_text('utf-8'))
        else:
            src = canonical_source()
            for table, rows in src.items():
                if isinstance(rows, list):
                    for row in rows:
                        row['company_id'] = cid
                        if table == 'companies':
                            row['record_id'] = cid
                            row['name'] = f'Doanh nghiệp mô phỏng {cid}'
                        if 'amount_vnd' in row:
                            row['amount_vnd'] = int(row['amount_vnd']) * scale
                        for line in row.get('accounting_lines', []):
                            line['debit_vnd'] = int(line['debit_vnd']) * scale
                            line['credit_vnd'] = int(line['credit_vnd']) * scale
        scope = auth.authorize(header, cid)
        check = lambda c=cid: auth.authorize(header, c)
        key_base = 'runtime-bootstrap-' + cid.lower()
        draft = snapshots.upload(scope, canonical(src), f'bootstrap-{cid}.json', key_base + '-up', check)
        prev = snapshots.preview(scope, draft['import_id'], draft['revision'], check)
        req = {k: prev[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
        req.update(expected_revision=prev['revision'], acknowledge=True)
        snap_id = snapshots.commit(scope, draft['import_id'], req, key_base + '-commit', check)['snapshot']['snapshot_id']

        def fit_cfg(m):
            return {
                'version': 'company-fit-config/1.0.0',
                'snapshot_id': snap_id,
                'method_id': m,
                'missing_policy': 'median_flags',
                'minimum_history': 5,
                'profile_id': 'synthetic-technical-demo-not-D03-production',
                'evaluation_mode': 'backtest',
                'history_start': '2026-09-02T00:00:00+07:00',
                'history_end': '2026-09-12T00:00:00+07:00',
                'reference_start': '2026-09-15T00:00:00+07:00',
                'reference_end': '2026-09-20T00:00:00+07:00',
                'evaluation_start': '2026-10-01T00:00:00+07:00',
            }

        rz = run_fit_job(snapshots, models, auth, header, cid, fit_cfg('robust_z'), key_base + '-rz')
        ml = run_fit_job(snapshots, models, auth, header, cid, fit_cfg(ml_method), key_base + '-' + ml_method)
        bindings.append({
            'tenant_id': 'demo',
            'company_id': cid,
            'statistics_artifact_id': rz['job']['artifact_id'],
            'ml_artifacts': {ml_method: ml['job']['artifact_id']},
        })

    bindings_path.write_bytes(canonical({'version': BINDINGS_VERSION, 'bindings': bindings}))
    print(f'[agent2] Đã khởi tạo models-v2.sqlite3 & analysis-bindings.json cho {[c for c, _, _ in target_companies]}', flush=True)
"""


def ensure_agent2_models() -> None:
    if port_open(8766):
        # Agent 2 is currently holding SQLite open; caller should stop old processes first if re-provisioning
        bindings_path = ROOT / 'agent2/.runtime/platform/analysis-bindings.json'
        if bindings_path.is_file():
            return
        print('[agent2] Cổng 8766 đang mở; bỏ qua ghi trực tiếp SQLite khi Agent 2 đang chạy.', flush=True)
        return
    py2 = find_venv_python('agent2')
    subprocess.run(
        [py2, '-X', 'utf8', '-B', '-c', AGENT2_PROVISION_SNIPPET, str(ROOT)],
        cwd=ROOT / 'agent2',
        env=dict(os.environ, PYTHONUTF8='1'),
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('auto', 'fast', 'full'), default='auto')
    args = parser.parse_args()

    warehouse = ensure_dataset(args.mode)
    sync_portal_files(warehouse)
    ensure_agent2_models()
    print(f'[ok] Đã đồng bộ cấu hình & dữ liệu. Kho Agent 4: {warehouse.relative_to(ROOT)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
