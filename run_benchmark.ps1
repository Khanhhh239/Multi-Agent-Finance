param(
    [int]$Rows = 100000,
    [int]$Seed = 20261012,
    [string]$OutputRoot = 'data',
    [string]$ReportRoot = 'reports',
    [string]$PythonExecutable = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $PythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $PythonExecutable = $pythonCommand.Source
    } else {
        $runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $runtimePython) {
            $PythonExecutable = $runtimePython
        } else {
            throw 'Không tìm thấy Python. Cài Python 3.10+ hoặc truyền -PythonExecutable.'
        }
    }
}
foreach ($scenario in @(@{Tag='001'; Rate='0.001'}, @{Tag='003'; Rate='0.003'}, @{Tag='005'; Rate='0.005'})) {
    $datasetPath = Join-Path $OutputRoot "sme_fraud_$($scenario.Tag)"
    $reportPath = Join-Path $ReportRoot "sme_fraud_$($scenario.Tag)"
    & $PythonExecutable -m sme_fraud.generate --output $datasetPath --rows $Rows --fraud-rate $scenario.Rate --seed $Seed
    if ($LASTEXITCODE -ne 0) { throw 'Sinh dữ liệu thất bại.' }
    & $PythonExecutable -m sme_fraud.validate --data $datasetPath
    if ($LASTEXITCODE -ne 0) { throw 'Kiểm tra dữ liệu thất bại.' }
    & $PythonExecutable -m sme_fraud.evaluate --data $datasetPath --output $reportPath --seed $Seed
    if ($LASTEXITCODE -ne 0) { throw 'Huấn luyện/đánh giá thất bại. Kiểm tra requirements.txt.' }
}
