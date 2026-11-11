param(
    [ValidateSet('core','large','lifecycle','pagination')][string]$Suite='core',
    [ValidatePattern('^[A-Za-z0-9_-]{1,24}$')][string]$RunId='run1',
    [ValidateRange(1,65535)][int]$Port=8021,
    [switch]$DryRun
)
$ErrorActionPreference='Stop'
$agentDirectory=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$repositoryDirectory=Split-Path -Parent $agentDirectory
$pythonCandidates=@((Join-Path $repositoryDirectory '.venv\Scripts\python.exe'),(Join-Path $agentDirectory '.venv\Scripts\python.exe'))
$pythonExecutable=$pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonExecutable) { throw 'Python .venv not found. Use an environment with requirements-service.txt installed.' }
$storageDirectory=Join-Path $agentDirectory ".state-uat-$Suite-$RunId"
$keyDirectory=$storageDirectory+'-keys'
$companyCode=('DEMO_T0T9_'+$Suite+'_'+$RunId).ToUpperInvariant()
Write-Host "UAT company: $companyCode"
Write-Host "Open: http://127.0.0.1:$Port/workspace#data"
Write-Host "Access key file: $keyDirectory\api-token.txt"
Write-Host "Data directory: $storageDirectory"
if ($DryRun) { return }
$savedEnvironment=@{}
Get-ChildItem Env:AGENT1_* | ForEach-Object { $savedEnvironment[$_.Name]=$_.Value }
$savedPythonUtf8=$env:PYTHONUTF8
$savedOmpThreads=$env:OMP_NUM_THREADS
$oldLocation=Get-Location
try {
    Get-ChildItem Env:AGENT1_* | ForEach-Object { Remove-Item -LiteralPath ('Env:'+$_.Name) }
    $env:PYTHONUTF8='1'
    $env:OMP_NUM_THREADS='2'
    $env:AGENT1_STATE_DIR=$storageDirectory
    $env:AGENT1_KEY_DIR=$keyDirectory
    $env:AGENT1_FIRM_ID=$companyCode
    $env:AGENT1_RESEARCH_MODE='0'
    $env:AGENT1_DEMO_TRAINING='0'
    Set-Location -LiteralPath $agentDirectory
    & $pythonExecutable -m uvicorn agent1_service.main:app --host 127.0.0.1 --port $Port
} finally {
    Set-Location -LiteralPath $oldLocation.Path
    Get-ChildItem Env:AGENT1_* | ForEach-Object { Remove-Item -LiteralPath ('Env:'+$_.Name) }
    foreach ($name in $savedEnvironment.Keys) { Set-Item -LiteralPath ('Env:'+$name) -Value $savedEnvironment[$name] }
    $env:PYTHONUTF8=$savedPythonUtf8
    $env:OMP_NUM_THREADS=$savedOmpThreads
}
