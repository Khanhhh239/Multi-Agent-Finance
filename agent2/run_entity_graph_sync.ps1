param(
    [string]$PythonExecutable = "python",
    [string]$Data = "data/feature_model_sync_20261017/sme_fraud_003",
    [string]$Output = ".runtime/entity_graph/sme_fraud_003",
    [int]$IntervalSeconds = 3600,
    [switch]$Once,
    [string]$AsOf = ""
)

$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
try {
    $GraphArguments = @("-B", "-m", "sme_fraud.sync_entity_graph", "--data", $Data, "--output", $Output)
    if ($Once) {
        if ($AsOf) { $GraphArguments += @("--as-of", $AsOf) }
    } else {
        if ($AsOf) { throw "Use -Once with -AsOf for a historical snapshot." }
        $GraphArguments += @("--watch", "--interval-seconds", [string]$IntervalSeconds)
    }
    & $PythonExecutable @GraphArguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
