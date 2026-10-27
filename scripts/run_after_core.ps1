param([int]$CoreProcessId)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:PYTHONUTF8='1';$env:AGENT1_THREADS='4';$env:OMP_NUM_THREADS='4'
if($CoreProcessId){while(Get-Process -Id $CoreProcessId -ErrorAction SilentlyContinue){Start-Sleep -Seconds 10}}
Push-Location $taskRoot
try {
    & $taskPython scripts/archive_t6.py
    if ($LASTEXITCODE -ne 0) { throw 'T6 archive failed' }
    & $taskPython -u scripts/run_plan.py --jobs T6-v5,C,seeds,T4,Berka,noisy-build,noisy-EF,tune,report
    if ($LASTEXITCODE -ne 0) { throw 'Remaining jobs failed' }
} finally { Pop-Location }
