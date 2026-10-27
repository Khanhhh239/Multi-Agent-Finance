$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:PYTHONUTF8='1';$env:AGENT1_THREADS='2';$env:OMP_NUM_THREADS='2'
Push-Location $taskRoot
try {
    & $taskPython -u scripts/build_hard_cases.py *> outputs/hard_cases_build.log
    if ($LASTEXITCODE -ne 0) { throw 'Hard-case generation failed' }
    & $taskPython -u scripts/build_multiworld.py --generate *> outputs/multiworld_build.log
    if ($LASTEXITCODE -ne 0) { throw 'Multiworld generation failed' }
    & $taskPython scripts/world_registry.py
    if ($LASTEXITCODE -ne 0) { throw 'World registry validation failed' }
} finally { Pop-Location }
