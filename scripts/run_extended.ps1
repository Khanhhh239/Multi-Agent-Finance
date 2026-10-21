$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:PYTHONUTF8='1';$env:AGENT1_THREADS='4';$env:OMP_NUM_THREADS='4'
Push-Location $taskRoot
try {
    & $taskPython -u scripts/run_t1.py --exp C *> outputs/implementation/C.log
    & $taskPython -u scripts/run_seed_stability.py *> outputs/implementation/seeds.log
    & $taskPython -u scripts/tune_t1.py *> outputs/implementation/tuning.log
    & $taskPython scripts/make_report.py
} finally { Pop-Location }
