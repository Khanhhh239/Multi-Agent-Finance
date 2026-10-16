$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
& "$PSScriptRoot/../.venv/Scripts/python.exe" -m pytest @args
exit $LASTEXITCODE
