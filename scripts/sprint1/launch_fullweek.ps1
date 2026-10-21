$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Item -LiteralPath $PSScriptRoot).Parent.Parent.FullName
$implementation = Join-Path $projectRoot 'outputs/implementation'
$statePath = Join-Path $implementation 'fullweek_refresh.json'
$records = @(Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json)
$latest = @{}
foreach ($record in $records) { $latest[$record.job] = $record }
if (@($latest.Values | Where-Object { $_.status -eq 'running' }).Count -gt 0) {
    throw 'A model job is running. Leave it intact; detach only at a RAM-wait boundary.'
}
# Only replace this project's waiting controller processes; never stop other projects.
$controllers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match 'scripts/sprint1/fullweek_(refresh|finish).py'
})
$controllerIds = @($controllers | ForEach-Object { $_.ProcessId })
$children = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ParentProcessId -in $controllerIds -and $_.CommandLine -match 'run_plan.py'
})
if ($children.Count -gt 0) { throw 'A training child started; leave it intact.' }
foreach ($controller in $controllers) { Stop-Process -Id $controller.ProcessId -ErrorAction SilentlyContinue }
# Refuse a duplicate run if a job forked during the boundary check.
$records = @(Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json)
$latest = @{}
foreach ($record in $records) { $latest[$record.job] = $record }
if (@($latest.Values | Where-Object { $_.status -eq 'running' }).Count -gt 0) {
    throw 'A child forked at detach time; inspect and adopt it before restarting.'
}
$env:AGENT1_THREADS = '4'
$env:OMP_NUM_THREADS = '4'
$env:PYTHONUTF8 = '1'
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
$refresh = Start-Process -FilePath $pythonPath -ArgumentList @('-u','scripts/sprint1/fullweek_refresh.py','--poll-seconds','10') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $implementation 'fullweek_refresh.detached.log') `
    -RedirectStandardError (Join-Path $implementation 'fullweek_refresh.detached.error.log')
$finish = Start-Process -FilePath $pythonPath -ArgumentList @('-u','scripts/sprint1/fullweek_finish.py','--publish') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $implementation 'fullweek_finish.detached.log') `
    -RedirectStandardError (Join-Path $implementation 'fullweek_finish.detached.error.log')
@{ refresh_pid=$refresh.Id; finish_pid=$finish.Id; mode='hidden_detached'; publish_after_complete=$true } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $implementation 'fullweek_workers.json') -Encoding utf8
Write-Output "Started hidden workers: refresh=$($refresh.Id), finish=$($finish.Id)"
