<#
.SYNOPSIS
  Cài đặt trọn gói môi trường Python (.venv), mô hình Ollama, kho luật Agent 3 và dữ liệu cho máy mới.
.EXAMPLE
  .\setup_all.ps1
  .\setup_all.ps1 -FullData
#>
param(
    [switch]$FullData,
    [switch]$SkipOllama,
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
    uv pip install -q -p agent1/.venv -r agent1/requirements-service.txt
    Push-Location agent2
    uv pip install -q -p .venv/Scripts/python.exe -r requirements.txt cryptography
    Pop-Location
    uv pip install -q -p agent4/.venv -r agent4/requirements.txt
    uv pip install -q -p agent4/.venv -e agent4 --no-deps

    $a3Core = Get-Content 'agent3/agent3_tax_compliance/requirements.txt' | Where-Object { $_ -notmatch '^(torch|transformers|sentence-transformers|sentencepiece|protobuf|pytest|hypothesis)' }
    $tmpReq = Join-Path $env:TEMP 'a3core_req.txt'
    Set-Content -LiteralPath $tmpReq -Value $a3Core -Encoding UTF8
    uv pip install -q -p agent3/.venv -r $tmpReq
    uv pip install -q -p agent3/.venv torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
    uv pip install -q -p agent3/.venv transformers==4.51.3 sentence-transformers==3.4.1 sentencepiece protobuf huggingface_hub
} else {
    & agent1\.venv\Scripts\python.exe -m pip install -q -r agent1/requirements-service.txt
    Push-Location agent2
    & .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt cryptography
    Pop-Location
    & agent4\.venv\Scripts\python.exe -m pip install -q -r agent4/requirements.txt
    & agent4\.venv\Scripts\python.exe -m pip install -q -e agent4 --no-deps
    & agent3\.venv\Scripts\python.exe -m pip install -q -r agent3/agent3_tax_compliance/requirements.txt huggingface_hub
}

if (-not $SkipOllama) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollama) {
        Write-Host "[2/4] Kiểm tra và tải mô hình Ollama..." -ForegroundColor Cyan
        foreach ($m in @('qwen3:8b', 'qwen3:4b-instruct-2507-q4_K_M', 'bge-m3', 'qwen3-embedding:0.6b', 'qwen2.5:0.5b')) {
            ollama pull $m
        }
    } else {
        Write-Host "[2/4] Bỏ qua Ollama (chưa cài đặt trên PATH)." -ForegroundColor Yellow
    }
}

if (-not $SkipLawSync) {
    Write-Host "[3/4] Chuẩn bị kho luật & mô hình xếp hạng lại cho Agent 3..." -ForegroundColor Cyan
    $py3 = (Resolve-Path 'agent3\.venv\Scripts\python.exe').Path
    Push-Location 'agent3/agent3_tax_compliance'
    if (-not (Test-Path -LiteralPath 'data/lawbase/lawbase.sqlite')) {
        & $py3 -m src.lawbase.cli sync
        & $py3 -m src.lawbase.dense build
    }
    if (-not (Test-Path -LiteralPath 'models/Vietnamese_Reranker/config.json')) {
        & $py3 -c "from huggingface_hub import snapshot_download as s; s('AITeamVN/Vietnamese_Reranker', local_dir='models/Vietnamese_Reranker')"
    }
    Pop-Location
}

Write-Host "[4/4] Tạo dữ liệu và đồng bộ cấu hình hệ thống..." -ForegroundColor Cyan
if ($FullData) {
    & "$PSScriptRoot\create_data.ps1" -Full
} else {
    & "$PSScriptRoot\create_data.ps1"
}

Write-Host "[ok] Cài đặt hoàn tất! Chạy .\run_web.ps1 để bật toàn bộ hệ thống." -ForegroundColor Green
