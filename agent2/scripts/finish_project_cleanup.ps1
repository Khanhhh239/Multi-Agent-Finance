# Remove only the reviewed cleanup list. Run manually in an elevated PowerShell.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$cleanupRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cleanupPrefix = $cleanupRoot.TrimEnd('\') + '\'
$cleanupPlanPath = Join-Path $cleanupRoot 'docs\history\pending_cleanup_20261027.json'
$cleanupIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$cleanupPrincipal = New-Object Security.Principal.WindowsPrincipal($cleanupIdentity)
if (-not $cleanupPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell with Run as administrator, then run this script. Nothing was deleted.'
}
$cleanupPlan = Get-Content -LiteralPath $cleanupPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cleanupDeleted = 0
$cleanupMissing = 0
$cleanupChanged = @()
foreach ($cleanupEntry in $cleanupPlan) {
    if ([IO.Path]::IsPathRooted($cleanupEntry.path)) { throw 'Absolute cleanup path rejected.' }
    $cleanupTarget = [IO.Path]::GetFullPath((Join-Path $cleanupRoot $cleanupEntry.path))
    if (-not $cleanupTarget.StartsWith($cleanupPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Cleanup path leaves workspace.'
    }
    $cleanupRelative = $cleanupEntry.path.Replace('\', '/')
    if ($cleanupEntry.kind -eq 'document_redirect') {
        if (-not ($cleanupRelative.StartsWith('reports/') -and $cleanupRelative.EndsWith('.md'))) {
            throw 'Unexpected document path.'
        }
    } elseif ($cleanupEntry.kind -eq 'bytecode') {
        if (-not ($cleanupRelative -match '^(sme_fraud|tests|\.runtime)/__pycache__/[^/]+\.pyc$')) {
            throw 'Unexpected bytecode path.'
        }
    } else { throw 'Unknown cleanup entry.' }
    $cleanupAncestor = [IO.Path]::GetDirectoryName($cleanupTarget)
    while ($cleanupAncestor.StartsWith($cleanupPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $cleanupAncestor) {
            if ((Get-Item -LiteralPath $cleanupAncestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Linked cleanup directory rejected.'
            }
        }
        $cleanupAncestor = [IO.Path]::GetDirectoryName($cleanupAncestor)
    }
    if (-not (Test-Path -LiteralPath $cleanupTarget)) { $cleanupMissing++; continue }
    $cleanupItem = Get-Item -LiteralPath $cleanupTarget -Force
    if ($cleanupItem.PSIsContainer -or ($cleanupItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Cleanup target must be a regular file.'
    }
    $cleanupHash = (Get-FileHash -LiteralPath $cleanupTarget -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($cleanupHash -ne $cleanupEntry.sha256) {
        $cleanupChanged += $cleanupEntry.path
        continue
    }
    Remove-Item -LiteralPath $cleanupTarget -Force
    $cleanupDeleted++
}
[pscustomobject]@{ Deleted = $cleanupDeleted; AlreadyMissing = $cleanupMissing; ChangedAndKept = $cleanupChanged } | ConvertTo-Json
if ($cleanupChanged.Count -gt 0) { Write-Warning 'Changed files were kept. Review them separately.' }
