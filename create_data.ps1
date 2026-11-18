<#
.SYNOPSIS
  Tạo và đồng bộ toàn bộ dữ liệu cho 4 Agent + gói chứng từ nạp thử MPX10 chỉ với 1 lệnh.
.EXAMPLE
  .\create_data.ps1          # Nhanh: giải nén kho có sẵn hoặc tạo gói mẫu + đồng bộ mô hình
  .\create_data.ps1 -Full    # Đầy đủ: sinh mới toàn bộ kho MPX10 4 năm (2023-2026), kiểm định, xuất CSV/XML cho A1-A4
#>
param(
    [switch]$Full
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'

$py = 'agent4\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    $py = (Get-Command python -ErrorAction Stop).Source
}

$mode = if ($Full) { 'full' } else { 'auto' }
Write-Host "[data] Chế độ tạo và đồng bộ dữ liệu: $mode" -ForegroundColor Cyan
& $py -X utf8 data_pipeline/setup_runtime.py --mode $mode

Write-Host ""
Write-Host "[ok] Hoàn tất! Gói 4 tệp nạp thử nằm tại: portal\workspace\mpx10-demo-input-full" -ForegroundColor Green
Write-Host "     Chạy .\run_web.ps1 để bật hệ thống web." -ForegroundColor White
