[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Verify', 'Compact', 'Restore')]
    [string]$Action = 'Verify',
    [string]$RelativePath = ''
)

# Compact immutable artifacts without removing historical paths. Restore creates
# independent copies again; it does not change any model or preservation hash.
$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char[]]'\/')
$workspacePrefix = $workspacePath + [IO.Path]::DirectorySeparatorChar
$manifestRelative = 'outputs/maintenance/unified_v2_hardlink_dedup_20261105.json'
$retainedPrefix = 'outputs/data/unified_collection_v2_20261104_r3/'
$duplicatePrefixes = @(
    'outputs/data/unified_collection_v2_20261104/',
    'outputs/data/unified_collection_v2_20261104_r2/'
)

function Get-SafePath([string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) {
        throw "Invalid relative path: $Relative"
    }
    $full = [IO.Path]::GetFullPath((Join-Path $workspacePath $Relative))
    if (-not $full.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path leaves workspace: $Relative"
    }
    $ancestor = $full
    while ($ancestor -ne $workspacePath) {
        if (Test-Path -LiteralPath $ancestor) {
            if (((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Linked path rejected: $Relative"
            }
        }
        $ancestor = Split-Path -Path $ancestor -Parent
    }
    return $full
}

function Get-Digest([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$manifest = Get-Content -LiteralPath (Get-SafePath $manifestRelative) -Raw | ConvertFrom-Json
$allEntries = @($manifest.duplicate_payloads)
if ($manifest.method -ne 'hardlink_to_r3' -or $allEntries.Count -ne 108) {
    throw 'Unexpected compaction manifest'
}
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $allEntries) {
    $prefix = @($duplicatePrefixes | Where-Object { $entry.path.StartsWith($_, [StringComparison]::Ordinal) })
    if ($prefix.Count -ne 1 -or -not $seen.Add($entry.path)) { throw "Unexpected duplicate path: $($entry.path)" }
    $suffix = $entry.path.Substring($prefix[0].Length)
    if ($suffix -match '(^|/)[.]{1,2}(/|$)' -or $suffix.Contains('\') -or
        $entry.retained_path -ne ($retainedPrefix + $suffix) -or $entry.sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "Invalid duplicate mapping: $($entry.path)"
    }
}
$entries = $allEntries
if ($RelativePath) {
    $entries = @($allEntries | Where-Object { $_.path -ceq $RelativePath })
    if ($entries.Count -ne 1) { throw 'RelativePath must exactly match one manifest entry' }
}

# Validate all selected mappings before any mutation. Backup names are checked
# for collisions; on an error each original file is put back immediately.
$pending = @(foreach ($entry in $entries) {
    $destination = Get-SafePath $entry.path
    $source = Get-SafePath $entry.retained_path
    $backup = Get-SafePath ($entry.path + '.dedup-backup')
    if (Test-Path -LiteralPath $backup) { throw "Recovery backup already exists: $backup" }
    foreach ($path in @($source, $destination)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-Item -LiteralPath $path).Length -ne $entry.bytes -or (Get-Digest $path) -ne $entry.sha256) {
            throw "Artifact differs from manifest: $path"
        }
    }
    [pscustomobject]@{ Entry = $entry; Source = $source; Destination = $destination; Backup = $backup }
})

$changed = 0
if ($Action -ne 'Verify') {
    foreach ($item in $pending) {
        if (-not $PSCmdlet.ShouldProcess($item.Destination, $Action)) { continue }
        # Recheck before rename to avoid replacing a file edited after preflight.
        if ((Get-Digest $item.Destination) -ne $item.Entry.sha256 -or
            (Get-Digest $item.Source) -ne $item.Entry.sha256) { throw 'Artifact changed after preflight' }
        Move-Item -LiteralPath $item.Destination -Destination $item.Backup
        try {
            if ($Action -eq 'Compact') {
                New-Item -ItemType HardLink -Path $item.Destination -Value $item.Source | Out-Null
            } else {
                Copy-Item -LiteralPath $item.Source -Destination $item.Destination
                $restored = Get-Item -LiteralPath $item.Destination
                $restored.CreationTimeUtc = [datetime]::Parse($item.Entry.original_creation_time_utc).ToUniversalTime()
                $restored.LastWriteTimeUtc = [datetime]::Parse($item.Entry.original_last_write_time_utc).ToUniversalTime()
                $restored.Attributes = [IO.FileAttributes][int]$item.Entry.original_attributes
            }
            if ((Get-Digest $item.Destination) -ne $item.Entry.sha256) { throw 'Post-operation hash mismatch' }
        } catch {
            $failure = $_
            if (Test-Path -LiteralPath $item.Destination) { Remove-Item -LiteralPath $item.Destination -Force }
            Move-Item -LiteralPath $item.Backup -Destination $item.Destination
            throw $failure
        }
        Remove-Item -LiteralPath $item.Backup -Force
        $changed++
    }
}
[pscustomobject]@{ Action = $Action; Verified = $pending.Count; Changed = $changed }
