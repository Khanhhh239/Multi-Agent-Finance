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
    [switch]$StopOnly,
    [switch]$SkipHE
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Stop-PlatformPorts {
    $ports = @(8800, 8011, 8766, 8640, 8040, 8868, 8869, 8870, 8890)
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
    # Các worker mã hóa chạy trong WSL; tắt WSL để trả lại RAM.
    if (Get-Command wsl -ErrorAction SilentlyContinue) { wsl --shutdown 2>$null | Out-Null }
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

# Dữ liệu đi kèm file nộp nhưng không nằm trong git (kho luật Agent 3): cài từ assets/ nếu chưa có.
& $py -X utf8 scripts/install_assets.py

# API key cho Agent 3/4 nằm trong một file .env duy nhất ở thư mục gốc (không đưa lên git).
# Thiếu thì 2 agent này offline, các agent khác vẫn chạy.
if (-not (Test-Path -LiteralPath '.env')) {
    Write-Host "[env] Thiếu file .env ở thư mục gốc: Agent 3 và Agent 4 sẽ offline. Chép file .env được gửi kèm vào thư mục gốc (mẫu: .env.example)." -ForegroundColor Yellow
}

# HE: lần đầu tự sinh khóa, mạch mã hóa, cấu hình và dữ liệu mẫu (scripts/setup_he.py), các lần sau bỏ qua.
# Bước này cần WSL (quyền quản trị, có thể phải khởi động lại Windows). Nếu chưa xong, web vẫn chạy
# không có HE và lần chạy sau sẽ thử lại; dùng -SkipHE để bỏ qua hẳn.
if (-not $SkipHE -and -not (Test-Path -LiteralPath '.runtime\he-ready.json')) {
    Write-Host "[he] Thiết lập mã hóa đồng cấu (HE) lần đầu, có thể mất 10-20 phút..." -ForegroundColor Cyan
    & $py -X utf8 scripts/setup_he.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[he] Chưa thiết lập được HE (xem thông báo phía trên). Web vẫn chạy, Agent 2 dùng chế độ không mã hóa." -ForegroundColor Yellow
    }
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

# Trạm huấn luyện mã hóa (web riêng, cổng 8890)
Start-Process -FilePath $py -ArgumentList '-X','utf8','station/server.py' -WindowStyle Hidden
Write-Host "  Trạm huấn luyện: http://127.0.0.1:8890" -ForegroundColor Gray

& $py -X utf8 portal/server.py --start-all
