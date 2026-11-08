param([ValidateRange(1,65535)][int]$Port=8011,[ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')][string]$Company='SME',[switch]$DemoTraining)
$ErrorActionPreference='Stop'
$projectDirectory=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
$pythonExecutable=Join-Path $projectDirectory '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Create .venv and install requirements-service.txt first. See agent1_service/README.md.'
}
$env:PYTHONUTF8='1'
$env:AGENT1_THREADS='4'
$env:OMP_NUM_THREADS='4'
$env:OPENBLAS_NUM_THREADS='1'
$Company=$Company.ToUpperInvariant()
$storageName=if ($Company -eq 'SME') { '.state-business' } else { ".state-business-firm-$Company-data" }
$env:AGENT1_STATE_DIR=Join-Path $projectDirectory $storageName
$env:AGENT1_KEY_DIR=Join-Path $projectDirectory ($storageName+'-keys')
$env:AGENT1_FIRM_ID=$Company
$env:AGENT1_RESEARCH_MODE='0'
if ($DemoTraining -and -not $Company.StartsWith('DEMO_')) { throw 'Demo training requires a separate DEMO_ company.' }
$env:AGENT1_DEMO_TRAINING=if ($DemoTraining) { '1' } else { '0' }
if ($DemoTraining) {
    $env:AGENT1_REPORT_PASSWORD_FILE=Join-Path $env:AGENT1_KEY_DIR 'report-password.txt'
    if (-not $env:AGENT1_REPORT_DIR) {
        $env:AGENT1_REPORT_DIR=Join-Path $projectDirectory 'outputs/private-training-reports'
    }
    New-Item -ItemType Directory -Path $env:AGENT1_KEY_DIR -Force | Out-Null
    if (-not (Test-Path -LiteralPath $env:AGENT1_REPORT_PASSWORD_FILE)) {
        $reportPasswordBytes=New-Object byte[] 32
        $reportRandomGenerator=[System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $reportRandomGenerator.GetBytes($reportPasswordBytes)
            [System.IO.File]::WriteAllText(
                $env:AGENT1_REPORT_PASSWORD_FILE,
                [Convert]::ToBase64String($reportPasswordBytes),
                [System.Text.UTF8Encoding]::new($false)
            )
        } finally {
            $reportRandomGenerator.Dispose()
        }
    }
    Write-Host "Training report password file: $env:AGENT1_REPORT_PASSWORD_FILE"
}
Write-Host "Agent1: http://127.0.0.1:$Port/workspace"
Write-Host "Access key: $storageName-keys/api-token.txt (keep private). Ctrl+C to stop."
& $pythonExecutable -m uvicorn agent1_service.main:app --host 127.0.0.1 --port $Port
