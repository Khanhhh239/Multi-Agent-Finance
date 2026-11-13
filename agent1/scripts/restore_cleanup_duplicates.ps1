[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$VerifyOnly,
    [string]$Run = ''
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'archive_common.psm1') -Force
$manifestPath = Get-SafePath 'outputs/maintenance/cleanup_2026-10-31.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$dataPrefix = 'data/T0/processed/'

function Get-SafeArchivePath([string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        [IO.Path]::IsPathRooted($RelativePath) -or
        -not $RelativePath.StartsWith($dataPrefix, [StringComparison]::Ordinal)) {
        throw "Invalid archive path: $RelativePath"
    }
    return Get-SafePath $RelativePath
}

$entries = @($manifest.duplicate_payloads)
if ($Run) {
    $runPrefix = $dataPrefix + $Run.TrimEnd('/') + '/'
    $entries = @($entries | Where-Object { $_.path.StartsWith($runPrefix, [StringComparison]::Ordinal) })
}
if ($entries.Count -eq 0) { throw 'No matching archived files.' }

# Validate every retained copy and existing destination before writing anything.
$sourceHashes = @{}
$pending = @()
foreach ($entry in $entries) {
    $sourcePath = Get-SafeArchivePath $entry.retained_path
    $destinationPath = Get-SafeArchivePath $entry.path
    if (-not $sourceHashes.ContainsKey($sourcePath)) {
        $sourceHashes[$sourcePath] = Get-Digest $sourcePath
    }
    if ($sourceHashes[$sourcePath] -ne $entry.sha256) {
        throw "Retained copy changed: $($entry.retained_path)"
    }
    if (Test-Path -LiteralPath $destinationPath) {
        if ((Get-Digest $destinationPath) -ne $entry.sha256) {
            throw "Destination contains different data; refusing to overwrite: $($entry.path)"
        }
    } else {
        $pending += [pscustomobject]@{ Source = $sourcePath; Destination = $destinationPath; Hash = $entry.sha256 }
    }
}

$restored = 0
if (-not $VerifyOnly) {
    foreach ($item in $pending) {
        if ($PSCmdlet.ShouldProcess($item.Destination, 'Restore duplicate from retained final archive')) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $item.Destination) -Force | Out-Null
            Copy-Item -LiteralPath $item.Source -Destination $item.Destination -ErrorAction Stop
            if ((Get-Digest $item.Destination) -ne $item.Hash) {
                throw "Restored hash mismatch: $($item.Destination)"
            }
            $restored++
        }
    }
}
[pscustomobject]@{ Verified = $entries.Count; MissingDuplicates = $pending.Count; Restored = $restored }
