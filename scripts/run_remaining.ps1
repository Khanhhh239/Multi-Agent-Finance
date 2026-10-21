param([int]$WaitProcessId=0)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:PYTHONUTF8='1';$env:OPENBLAS_NUM_THREADS='1'
if($WaitProcessId){Wait-Process -Id $WaitProcessId -ErrorAction SilentlyContinue}
Push-Location $taskRoot
try {
    & $taskPython -u scripts/run_plan.py --jobs noisy-EF,big,tune,tuned-eval,tests,report
    exit $LASTEXITCODE
} finally {Pop-Location}
