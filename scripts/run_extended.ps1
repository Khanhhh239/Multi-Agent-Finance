$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:PYTHONUTF8='1';$env:AGENT1_THREADS='4';$env:OMP_NUM_THREADS='4'
Push-Location $taskRoot
try {
    & $taskPython -u scripts/run_t1.py --exp C *> outputs/implementation/C.log
    if ($LASTEXITCODE -ne 0) { throw 'T1 C failed' }
    & $taskPython -u scripts/run_seed_stability.py *> outputs/implementation/seeds.log
    if ($LASTEXITCODE -ne 0) { throw 'Seed stability failed' }
    & $taskPython -u scripts/tune_t1.py *> outputs/implementation/tuning.log
    if ($LASTEXITCODE -ne 0) { throw 'T1 tuning failed' }
    & $taskPython scripts/make_report.py
    if ($LASTEXITCODE -ne 0) { throw 'Report generation failed' }
} finally { Pop-Location }
