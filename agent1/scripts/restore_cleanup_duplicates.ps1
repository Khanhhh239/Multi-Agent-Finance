[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$VerifyOnly,
    [string]$Run = ''
)

$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workspacePrefix = $workspacePath.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$manifestPath = Join-Path $workspacePath 'outputs/maintenance/cleanup_2026-10-31.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$dataPrefix = 'data/T0/processed/'

function Get-SafeArchivePath([string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        [IO.Path]::IsPathRooted($RelativePath) -or
        -not $RelativePath.StartsWith($dataPrefix, [StringComparison]::Ordinal)) {
        throw "Invalid archive path: $RelativePath"
    }
    $fullPath = [IO.Path]::GetFullPath((Join-Path $workspacePath $RelativePath))
    if (-not $fullPath.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Archive path leaves the workspace: $RelativePath"
    }
    $ancestorPath = $fullPath
    while ($ancestorPath -ne $workspacePath) {
        if (Test-Path -LiteralPath $ancestorPath) {
            $item = Get-Item -LiteralPath $ancestorPath -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Archive path contains a link: $RelativePath"
            }
        }
        $ancestorPath = Split-Path -Parent $ancestorPath
    }
    return $fullPath
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
        $sourceHashes[$sourcePath] = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
    }
    if ($sourceHashes[$sourcePath] -ne $entry.sha256) {
        throw "Retained copy changed: $($entry.retained_path)"
    }
    if (Test-Path -LiteralPath $destinationPath) {
        if ((Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash -ne $entry.sha256) {
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
            if ((Get-FileHash -LiteralPath $item.Destination -Algorithm SHA256).Hash -ne $item.Hash) {
                throw "Restored hash mismatch: $($item.Destination)"
            }
            $restored++
        }
    }
}
[pscustomobject]@{ Verified = $entries.Count; MissingDuplicates = $pending.Count; Restored = $restored }
