param([ValidateSet('test','lint','world-small','report','validate')][string]$Task = 'test')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:AGENT1_THREADS = '4'
$env:OMP_NUM_THREADS = '4'
$env:PYTHONUTF8 = '1'
Push-Location $taskRoot
try {
    switch ($Task) {
        'test' { & $taskPython -m pytest -q tests }
        'lint' { & $taskPython -m ruff check --select E9,F63,F7,F82 agent1 agent1_service scripts tests pilot }
        'world-small' { & $taskPython -c "from agent1.synth.world import WorldConfig, generate; generate(WorldConfig(name='smoke', n_firms=3, start='2023-01-01', end='2024-12-31', write_xml=0))" }
        'report' { & $taskPython scripts/make_report.py }
        'validate' { & $taskPython scripts/validate_worlds.py }
    }
    if ($LASTEXITCODE -ne 0) { throw "Task $Task failed (exit $LASTEXITCODE)" }
} finally { Pop-Location }
