#!/usr/bin/env python3
"""Build deploy/azure-vm/state for the public demo from a checkout where run_web.bat has already run.

The VM container does not run data_pipeline/setup_runtime.py, so the data that script generated on the team's
machine is collected here once and shipped to the VM as state/:

  demo/warehouse.duckdb                 Agent 4: full Minh Phat (MPX10) warehouse
  agent2/*.sqlite3, analysis-bindings   Agent 2: snapshots, fitted models and their bindings (via prepare-agent2-state.py;
                                        the case queue and remediation databases start empty on the VM)
  portal/agent2_access.json             Agent 2 access policy
  portal/company.json                   Shared company profile (MPX10)
  portal/agent1_profiles/<code>.json    Agent 1 profile for that company
  portal/intake_security.json           Fixed data-intake password (default SoSon@2026, as in the test kit)

Not copied: intake history (batches, audit, pending, bank_sources), Agent 1 data, HE/DPAPI keys and local config.

  python deploy/azure-vm/collect-state.py --source D:/SoSon_BTC_test/SoSon
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import secrets
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAREHOUSE = Path('portal/workspace/datasets/enterprise-x10-v3-full/warehouse.duckdb')


def load_prepare_module():
    spec = importlib.util.spec_from_file_location('prepare_agent2_state', HERE / 'prepare-agent2-state.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def intake_security(password: str) -> dict:
    # Same format and scrypt parameters as portal/server.py set_password() and reset_data_intake.ps1.
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return dict(salt=salt.hex(), hash=digest.hex(), created_at=time.strftime('%Y-%m-%d %H:%M:%S'))


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', type=Path, required=True, help='checkout where run_web.bat has run (has the full warehouse)')
    ap.add_argument('--output', type=Path, default=HERE / 'state')
    ap.add_argument('--intake-password', default='SoSon@2026')
    ap.add_argument('--force', action='store_true', help='replace files already in --output')
    a = ap.parse_args()
    src, out = a.source.resolve(), a.output.resolve()

    warehouse = src / WAREHOUSE
    company_file = src / 'portal/workspace/company.json'
    missing = [str(p.relative_to(src)) for p in (warehouse, company_file) if not p.is_file()]
    if missing:
        raise SystemExit('Thiếu trong --source: ' + ', '.join(missing) + ' (chạy run_web.bat hoặc create_data.ps1 -Full ở đó trước).')
    wal = warehouse.with_name(warehouse.name + '.wal')
    if wal.is_file() and wal.stat().st_size:
        raise SystemExit('Kho DuckDB đang được ghi (có tệp .wal). Tắt web ở --source (run_web.ps1 -StopOnly) rồi chạy lại.')
    if len(a.intake_password) < 8:
        raise SystemExit('Mật khẩu nạp dữ liệu cần ít nhất 8 ký tự.')
    if out.exists() and any(out.iterdir()) and not a.force:
        raise SystemExit(f'{out} đã có dữ liệu. Thêm --force để ghi đè.')

    company = json.loads(company_file.read_text(encoding='utf-8'))
    code = str(company.get('code') or '').strip().upper()
    if not code:
        raise SystemExit('company.json ở --source chưa có mã doanh nghiệp.')

    # 1. Agent 4 warehouse
    (out / 'demo').mkdir(parents=True, exist_ok=True)
    print(f'[1/4] Agent 4: chép kho {warehouse.stat().st_size / (1 << 30):.2f} GB ...', flush=True)
    shutil.copyfile(warehouse, out / 'demo/warehouse.duckdb')

    # 2. Agent 2 state and access policy, read from --source by the existing export script
    print('[2/4] Agent 2: snapshot, mô hình, binding và quyền truy cập ...', flush=True)
    prepare = load_prepare_module()
    prepare.REPO = src
    # The case queue and remediation databases are working queues: Agent 2 creates them empty at
    # AGENT2_CASE_QUEUE_DB / AGENT2_REMEDIATION_DB, and the public demo starts with no open cases.
    prepare.FILES = tuple(f for f in prepare.FILES if not f[0].endswith(('case-queue.sqlite3', 'remediation.sqlite3')))
    for name in prepare.prepare(out, force=a.force):
        print('      ' + name)

    # 3. Company profile for the Portal and Agent 1
    print(f'[3/4] Hồ sơ doanh nghiệp {code} ...', flush=True)
    (out / 'portal/agent1_profiles').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(company_file, out / 'portal/company.json')
    profile = src / f'portal/workspace/agent1_profiles/{code}.json'
    if profile.is_file():
        shutil.copyfile(profile, out / f'portal/agent1_profiles/{code}.json')
    else:
        print(f'      (không có agent1_profiles/{code}.json ở --source; Portal tạo lại khi lưu hồ sơ)')

    # 4. Fixed intake password
    print('[4/4] Mật khẩu nạp dữ liệu cố định ...', flush=True)
    (out / 'portal/intake_security.json').write_text(json.dumps(intake_security(a.intake_password)), encoding='utf-8')

    print(f'[ok] Đã dựng {out}')
    print('     Tiếp theo (Git Bash, trong deploy/azure-vm):  tar -czf ~/state-pristine.tgz state')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
