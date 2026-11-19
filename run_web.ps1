<#
.SYNOPSIS
  Khởi động toàn bộ nền tảng Sổ Son (Portal + 4 Agent) chỉ với 1 lệnh duy nhất.
.DESCRIPTION
  - Tự động dọn tiến trình cũ bị kẹt trên cổng 8800, 8011, 8766, 8640, 8040
  - Nạp API-key configuration cho các agent
  - Tự động đồng bộ cấu hình, hồ sơ doanh nghiệp, kho dữ liệu & mô hình Agent 1–4
  - Khởi chạy Portal cùng cả 4 Agent và mở trình duyệt tại http://127.0.0.1:8800
.EXAMPLE
  .\run_web.ps1
  .\run_web.ps1 -NoBrowser
  .\run_web.ps1 -StopOnly
#>
param(
    [switch]$NoBrowser,
    [switch]$StopOnly
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Stop-PlatformPorts {
    $ports = @(8800, 8011, 8766, 8640, 8040)
    $pids = @()
    foreach ($p in $ports) {
        $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            if ($c.OwningProcess -and $c.OwningProcess -gt 4 -and $c.OwningProcess -ne $PID) {
                $pids += $c.OwningProcess
            }
        }
    }
    $pids = $pids | Select-Object -Unique
    foreach ($procId in $pids) {
        Write-Host "[clean] Dừng tiến trình cũ (PID $procId)..." -ForegroundColor Yellow
        cmd /c "taskkill /PID $procId /T /F >nul 2>&1" | Out-Null
    }
    if ($pids.Count -gt 0) {
        Start-Sleep -Seconds 1
    }
}

Stop-PlatformPorts
if ($StopOnly) {
    Write-Host "[ok] Đã dừng toàn bộ Portal và 4 Agent." -ForegroundColor Green
    exit 0
}

# Kiểm tra môi trường Python của 4 agent
$missingVenv = @('agent1', 'agent2', 'agent3', 'agent4') | Where-Object { -not (Test-Path -LiteralPath "$_/.venv/Scripts/python.exe") }
if ($missingVenv.Count -gt 0) {
    Write-Host "[setup] Thiếu môi trường Python cho: $($missingVenv -join ', '). Đang chạy setup_all.ps1..." -ForegroundColor Cyan
    & "$PSScriptRoot\setup_all.ps1" -SkipLawSync
}

# Chọn Python điều phối (ưu tiên agent2/.venv có sẵn cryptography cho WebAuthn, hoặc python hệ thống)
$py = 'agent2\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    $py = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "[sync] Đồng bộ cấu hình, dữ liệu và mô hình cho Portal + 4 Agent..." -ForegroundColor Cyan
& $py -X utf8 data_pipeline/setup_runtime.py --mode auto

if (-not $NoBrowser) {
    $null = Start-Job -ScriptBlock {
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 500
            try {
                $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8800/api/state' -UseBasicParsing -TimeoutSec 2
                if ($r.StatusCode -eq 200) {
                    Start-Process 'http://127.0.0.1:8800'
                    break
                }
            } catch {}
        }
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  SỔ SON — VĂN PHÒNG KẾ TOÁN SỐ ĐA TÁC TỬ (4 AGENTS)" -ForegroundColor Green
Write-Host "  Web chung : http://127.0.0.1:8800" -ForegroundColor White
Write-Host "  Agent 1   : http://127.0.0.1:8011  (Dòng tiền)" -ForegroundColor Gray
Write-Host "  Agent 2   : http://127.0.0.1:8766  (Soát giao dịch)" -ForegroundColor Gray
Write-Host "  Agent 3   : http://127.0.0.1:8640  (Thuế GTGT)" -ForegroundColor Gray
Write-Host "  Agent 4   : http://127.0.0.1:8040  (Hỏi đáp số liệu CFO)" -ForegroundColor Gray
Write-Host "  Nhấn Ctrl+C để dừng toàn bộ hệ thống." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

& $py -X utf8 portal/server.py --start-all
