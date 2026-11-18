param([Parameter(Mandatory=$true)][ValidateSet('history','new','schedule')][string]$Phase)
$ErrorActionPreference = 'Stop'
$demoRepository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$demoPython = Join-Path $demoRepository '.venv/Scripts/python.exe'
& $demoPython -B -X utf8 (Join-Path $demoRepository 'agent1/scripts/business/load_company_demo_phase.py') $Phase
if ($LASTEXITCODE -ne 0) { throw ('Loading demo phase failed: ' + $Phase + '. Previously committed files are preserved; read the error before retrying.') }
