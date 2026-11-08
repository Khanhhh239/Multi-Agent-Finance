param(
    [string]$OutputRoot = 'reports/rules',
    [double]$AlertBudget = 0.003,
    [string]$PythonExecutable = '',
    [string]$Config = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $PythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $PythonExecutable = $pythonCommand.Source
    } else {
        $runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $runtimePython) { $PythonExecutable = $runtimePython }
        else { throw 'Không tìm thấy Python; truyền -PythonExecutable.' }
    }
}
foreach ($tag in @('001', '003', '005')) {
    $parameters = @('-m', 'sme_fraud.run_rules', '--data', "data/sme_fraud_$tag", '--output',
        (Join-Path $OutputRoot "sme_fraud_$tag"), '--if-model', "reports/sme_fraud_$tag/isolation_forest.joblib",
        '--alert-budget', $AlertBudget.ToString([System.Globalization.CultureInfo]::InvariantCulture))
    if ($Config) { $parameters += @('--config', $Config) }
    & $PythonExecutable @parameters
    if ($LASTEXITCODE -ne 0) { throw "Benchmark luật thất bại ở bộ $tag." }
    & $PythonExecutable -m sme_fraud.audit_rules --data "data/sme_fraud_$tag" --report (Join-Path $OutputRoot "sme_fraud_$tag")
    if ($LASTEXITCODE -ne 0) { throw "Đối soát kết quả luật thất bại ở bộ $tag." }
}
& $PythonExecutable -m sme_fraud.summarise_rules --reports $OutputRoot
if ($LASTEXITCODE -ne 0) { throw 'Tổng hợp benchmark luật thất bại.' }
