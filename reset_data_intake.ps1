<#
.SYNOPSIS
  Đặt lại trạng thái nạp chứng từ của hồ sơ MPX10 về ban đầu (mật khẩu mở khóa: SoSon@2026) để thực hành kéo-thả nạp dữ liệu lại từ đầu.
#>
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

& "$PSScriptRoot\run_web.ps1" -StopOnly

$py = 'agent2\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    $py = (Get-Command python -ErrorAction Stop).Source
}

& $py -X utf8 -c @"
import hashlib, json, secrets, shutil, time
from pathlib import Path

root = Path(r'$PSScriptRoot')
work = root / 'portal/workspace'
work.mkdir(parents=True, exist_ok=True)

# Clean pending, batches, audit, bank_sources for fresh intake demo
for sub in ('pending', 'bank_sources'):
    p = work / sub
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)

for f in ('batches.json', 'audit.jsonl'):
    p = work / f
    if p.exists():
        p.unlink()

# Reset Agent 1 MPX10 state & Agent 3 MPX10 workspace files (preserve pack.json)
for p in root.glob('agent1/.state-business-firm-MPX10*'):
    if p.is_dir():
        shutil.rmtree(p)

a3_ws = work / 'agent3/workspaces/0999999905'
if a3_ws.exists():
    for item in a3_ws.iterdir():
        if item.name != 'pack.json':
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

# Set clean, memorable password: SoSon@2026
pw = 'SoSon@2026'
salt = secrets.token_bytes(16)
dk = hashlib.scrypt(pw.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)
(work / 'intake_security.json').write_text(
    json.dumps({'salt': salt.hex(), 'hash': dk.hex(), 'created_at': time.strftime('%Y-%m-%d %H:%M:%S')}, indent=1),
    encoding='utf-8',
)
(work / 'intake-test-password.txt').write_text(pw, encoding='utf-8')
print('[ok] Đã đặt lại trạng thái nạp dữ liệu MPX10. Mật khẩu mở khóa: SoSon@2026')
"@

& $py -X utf8 data_pipeline/setup_runtime.py --mode auto
Write-Host "[ok] Sẵn sàng! Chạy .\run_web.ps1 để bật lại hệ thống." -ForegroundColor Green
