# Starts the platform shell and all four agents. Open http://127.0.0.1:8800 afterwards; Ctrl+C stops everything.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'portal/config.local.json')) {
    Copy-Item 'portal/config.example.json' 'portal/config.local.json'
    Write-Host 'Created portal/config.local.json from the example. Set "python" for agents without their own .venv.'
}
$python = (Get-Command python -ErrorAction Stop).Source
& $python -X utf8 portal/server.py --start-all
