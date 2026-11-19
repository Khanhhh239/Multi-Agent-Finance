<#
.SYNOPSIS
  Cài đặt trọn gói môi trường Python (.venv), kho luật Agent 3 và dữ liệu cho máy mới.
.EXAMPLE
  .\setup_all.ps1
  .\setup_all.ps1 -FullData
#>
param(
    [switch]$FullData,
    [switch]$SkipLawSync
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'

Write-Host "[1/4] Cài đặt môi trường Python (.venv) cho 4 Agent..." -ForegroundColor Cyan
$hasUv = $null -ne (Get-Command uv -ErrorAction SilentlyContinue)

foreach ($a in @('agent1', 'agent2', 'agent3', 'agent4')) {
    if (-not (Test-Path -LiteralPath "$a/.venv/Scripts/python.exe")) {
        Write-Host "  -> Tạo $a/.venv"
        if ($hasUv) {
            uv venv -q -p 3.12 "$a/.venv"
        } else {
            python -m venv "$a/.venv"
        }
    }
}

if ($hasUv) {
    Push-Location agent1
    uv pip install -q -p .venv -r requirements-service.txt
    Pop-Location
    Push-Location agent2
    uv pip install -q -p .venv/Scripts/python.exe -r requirements.txt cryptography
    Pop-Location
    Push-Location agent4
    uv pip install -q -p .venv -r requirements.txt
    uv pip install -q -p .venv -e . --no-deps
    Pop-Location

    uv pip install -q -p agent3/.venv -r agent3/agent3_tax_compliance/requirements.txt
} else {
    & agent1\.venv\Scripts\python.exe -m pip install -q -r agent1/requirements-service.txt
    Push-Location agent2
    & .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt cryptography
    Pop-Location
    & agent4\.venv\Scripts\python.exe -m pip install -q -r agent4/requirements.txt
    & agent4\.venv\Scripts\python.exe -m pip install -q -e agent4 --no-deps
    & agent3\.venv\Scripts\python.exe -m pip install -q -r agent3/agent3_tax_compliance/requirements.txt
}

if (-not $SkipLawSync) {
    Write-Host "[3/4] Chuẩn bị kho luật cho Agent 3..." -ForegroundColor Cyan
    $py3 = (Resolve-Path 'agent3\.venv\Scripts\python.exe').Path
    Push-Location 'agent3/agent3_tax_compliance'
    if (-not (Test-Path -LiteralPath 'data/lawbase/lawbase.sqlite')) {
        & $py3 -m src.lawbase.cli sync
    }
    Write-Host "  -> Agent 3 dùng embedding và reranker API khi được cấu hình key." -ForegroundColor Gray
    Pop-Location
}

Write-Host "[4/4] Tạo dữ liệu và đồng bộ cấu hình hệ thống..." -ForegroundColor Cyan
if ($FullData) {
    & "$PSScriptRoot\create_data.ps1" -Full
} else {
    & "$PSScriptRoot\create_data.ps1"
}

Write-Host "[ok] Cài đặt hoàn tất! Chạy .\run_web.ps1 để bật toàn bộ hệ thống." -ForegroundColor Green
