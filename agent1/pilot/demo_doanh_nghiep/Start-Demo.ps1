param([switch]$Fresh, [switch]$Stop, [switch]$Preload)
$ErrorActionPreference = 'Stop'
$demoRepository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$demoPython = Join-Path $demoRepository '.venv/Scripts/python.exe'
$demoLatestFile = Join-Path $demoRepository '.runtime/agent1-demo/latest.json'
if ($Fresh -and (Test-Path -LiteralPath $demoLatestFile)) {
    & $PSCommandPath -Stop
}
if ($Fresh -or -not (Test-Path -LiteralPath $demoLatestFile)) {
    Write-Host 'Preparing and validating the demo files. This can take a few minutes; the portal address is printed when ready.'
    $demoPrepareArgs = @('-B','-X','utf8',(Join-Path $demoRepository 'agent1/scripts/business/prepare_company_demo.py'))
    if ($Preload) { $demoPrepareArgs += '--preload' }
    & $demoPython @demoPrepareArgs
    if ($LASTEXITCODE -ne 0) { throw 'Preparing the demo failed.' }
}
$demoSetup = Get-Content -LiteralPath $demoLatestFile -Raw | ConvertFrom-Json
$demoPidFile = Join-Path $demoSetup.run 'portal-process.json'
if ($Stop) {
    if (Test-Path -LiteralPath $demoPidFile) {
        $demoProcessRecord = Get-Content -LiteralPath $demoPidFile -Raw | ConvertFrom-Json
        $demoProcessId = [int]$demoProcessRecord.id
        $demoProcess = Get-Process -Id $demoProcessId -ErrorAction SilentlyContinue
        if ($demoProcess -and $demoProcess.StartTime.ToUniversalTime().Ticks -eq ([datetime]$demoProcessRecord.started).ToUniversalTime().Ticks) {
            foreach ($demoAgentId in @('agent1','agent2','agent3','agent4')) {
                # The Portal refuses to stop services it does not own.
                try { Invoke-RestMethod -Uri ($demoSetup.portal_url + '/api/agents/' + $demoAgentId + '/stop') -Method Post -Headers @{'X-Platform'='1'} -TimeoutSec 15 | Out-Null } catch {}
            }
            Stop-Process -Id $demoProcessId
        }
    }
    Write-Host 'Stopped the isolated demo. Data has been preserved.'
    return
}
try {
    $demoHealth = Invoke-RestMethod -Uri ($demoSetup.portal_url + '/api/state') -TimeoutSec 2
    if ($demoHealth.company.code -ne $demoSetup.company) { throw 'Another portal is already using this port.' }
    $demoLiveKey = (Invoke-RestMethod -Uri ($demoSetup.portal_url + '/api/agents/agent1/key') -TimeoutSec 2).key
    $demoExpectedKey = (Get-Content -LiteralPath (Join-Path $demoSetup.keys 'api-token.txt') -Raw).Trim()
    if ($demoLiveKey -ne $demoExpectedKey) { throw 'A different demo run is already using this port. Stop that run first.' }
} catch {
    if ($_.Exception.Message -in @('Another portal is already using this port.', 'A different demo run is already using this port. Stop that run first.')) { throw }
    $env:MAF_PORTAL_CONFIG = $demoSetup.config
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $demoProcess = Start-Process -FilePath $demoPython -ArgumentList @('-B','-X','utf8','portal/server.py') `
        -WorkingDirectory $demoRepository -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $demoSetup.run 'portal.stdout.log') `
        -RedirectStandardError (Join-Path $demoSetup.run 'portal.stderr.log')
    @{id=$demoProcess.Id; started=$demoProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $demoPidFile -Encoding utf8
    $demoReady = $false
    for ($demoAttempt=0; $demoAttempt -lt 30; $demoAttempt++) {
        try { Invoke-RestMethod -Uri ($demoSetup.portal_url + '/api/state') -TimeoutSec 2 | Out-Null; $demoReady=$true; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $demoReady) { throw ('Portal did not start; check ' + $demoSetup.run) }
}
Invoke-RestMethod -Uri ($demoSetup.portal_url + '/api/agents/agent1/start') -Method Post -Headers @{'X-Platform'='1'} -TimeoutSec 90 | Out-Null
Invoke-RestMethod -Uri ($demoSetup.portal_url + '/api/agents/agent3/start') -Method Post -Headers @{'X-Platform'='1'} -TimeoutSec 90 | Out-Null
$demoAgentConfig = Get-Content -LiteralPath $demoSetup.config -Raw | ConvertFrom-Json
foreach ($demoService in @(
    @{name='Agent 1'; url=($demoSetup.agent_url + '/health')},
    @{name='Agent 3'; url=('http://127.0.0.1:' + $demoAgentConfig.agents.agent3.port + '/api/schema')}
)) {
    $demoServiceReady = $false
    $demoServiceDeadline = (Get-Date).AddSeconds(45)
    do {
        try { Invoke-RestMethod -Uri $demoService.url -TimeoutSec 2 | Out-Null; $demoServiceReady=$true } catch { Start-Sleep -Milliseconds 500 }
    } while (-not $demoServiceReady -and (Get-Date) -lt $demoServiceDeadline)
    if (-not $demoServiceReady) { throw ($demoService.name + ' did not become ready. Check ' + (Join-Path $demoSetup.run 'portal/logs') + '. Existing data has been preserved.') }
}
Write-Host ('Demo company: ' + $demoSetup.company)
Write-Host ('Open: ' + $demoSetup.portal_url)
Write-Host 'Agent 1 and Agent 3 are enabled for the shared bank intake; the presentation can stay in Cash flow.'
Write-Host ('Forecast date: ' + $demoSetup.cutoff + '; opening balance: 424000000 VND; floor: 200000000 VND; horizon: 13 weeks.')
Write-Host ('Intake password file: ' + $demoSetup.password_file)
Write-Host ('Sources preloaded: ' + [bool]$demoSetup.preloaded + '. Default -Fresh starts empty for history -> new documents -> reconciliation -> schedule.')
Write-Host 'Use Load-DemoPhase.ps1 to load one phase. Use -Fresh -Preload only for a preloaded backup. Previous runs are preserved.'
