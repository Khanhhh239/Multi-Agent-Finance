param(
    [string]$PythonExecutable = "python",
    [string]$Data = "data/feature_model_sync_20261017/sme_fraud_003",
    [string]$Output = ".runtime/dynamic_thresholds/sme_fraud_003",
    [string]$Config = "",
    [int]$IntervalSeconds = 3600,
    [switch]$Once,
    [string]$AsOf = ""
)

$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
try {
    $ThresholdArguments = @("-B", "-m", "sme_fraud.sync_dynamic_thresholds", "--data", $Data, "--output", $Output)
    if ($Config) { $ThresholdArguments += @("--config", $Config) }
    if ($Once) {
        if ($AsOf) { $ThresholdArguments += @("--as-of", $AsOf) }
    } else {
        if ($AsOf) { throw "Use -Once with -AsOf for a historical snapshot." }
        $ThresholdArguments += @("--watch", "--interval-seconds", [string]$IntervalSeconds)
    }
    & $PythonExecutable @ThresholdArguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
