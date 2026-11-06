[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Verify', 'Compact', 'Restore')]
    [string]$Action = 'Verify',
    [ValidateSet('All', '8', '9', '10')]
    [string]$Stage = 'All',
    [string]$RelativePath = ''
)

$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char[]]'\/')
$workspacePrefix = $workspacePath + [IO.Path]::DirectorySeparatorChar
function Get-SafePath([string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) { throw 'Invalid relative path' }
    $full = [IO.Path]::GetFullPath((Join-Path $workspacePath $Relative))
    if (-not $full.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Path leaves workspace: $Relative" }
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
function Get-Digest([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Test-Scope([string]$Relative, [string]$EntryStage) {
    if ($Relative.Contains('\') -or $Relative -match '(^|/)[.]{1,2}(/|$)') { return $false }
    switch ($EntryStage) {
        '8' { return $Relative -cmatch '^data/synthetic/(hc_|v3_candidate|v3_releasecheck|v[456]_lifecycle_control)[^/]+/[^/]+[.]parquet$' }
        '9' { return $Relative -cmatch '^data/T1/raw/(adjacent_source_research|late_only_augmentation)/' }
        '10' { return $Relative.StartsWith('outputs/', [StringComparison]::Ordinal) -and -not $Relative.StartsWith('outputs/maintenance/', [StringComparison]::Ordinal) }
    }
    return $false
}

$manifest = Get-Content -LiteralPath (Get-SafePath 'outputs/maintenance/research_hardlink_dedup_20261105.json') -Raw | ConvertFrom-Json
$allEntries = @($manifest.duplicate_payloads)
if ($manifest.method -ne 'hardlink_research_stages_8_9_10' -or $allEntries.Count -ne 333) { throw 'Unexpected research compaction manifest' }
$destinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$sources = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $allEntries) {
    if (-not (Test-Scope $entry.path ([string]$entry.stage)) -or -not (Test-Scope $entry.retained_path ([string]$entry.stage)) -or
        -not $destinations.Add($entry.path) -or $entry.path -eq $entry.retained_path -or
        $entry.sha256 -notmatch '^[0-9a-f]{64}$' -or $entry.bytes -lt 65536) { throw "Invalid duplicate mapping: $($entry.path)" }
    [void]$sources.Add($entry.retained_path)
}
foreach ($source in $sources) { if ($destinations.Contains($source)) { throw 'Retained source is also a replacement destination' } }
$entries = $allEntries
if ($Stage -ne 'All') { $entries = @($entries | Where-Object { [string]$_.stage -eq $Stage }) }
if ($RelativePath) {
    $entries = @($entries | Where-Object { $_.path -ceq $RelativePath })
    if ($entries.Count -ne 1) { throw 'RelativePath must match exactly one entry within the selected stage' }
}

$pending = @(foreach ($entry in $entries) {
    $destination = Get-SafePath $entry.path
    $source = Get-SafePath $entry.retained_path
    $backup = Get-SafePath ($entry.path + '.research-dedup-backup')
    if (Test-Path -LiteralPath $backup) { throw "Recovery backup already exists: $backup" }
    foreach ($path in @($source, $destination)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-Item -LiteralPath $path).Length -ne $entry.bytes -or (Get-Digest $path) -ne $entry.sha256) {
            throw "File differs from manifest: $path"
        }
    }
    [pscustomobject]@{ Entry = $entry; Source = $source; Destination = $destination; Backup = $backup }
})
$changed = 0
if ($Action -ne 'Verify') {
    foreach ($item in $pending) {
        if (-not $PSCmdlet.ShouldProcess($item.Destination, $Action)) { continue }
        if ((Get-Digest $item.Destination) -ne $item.Entry.sha256 -or
            (Get-Digest $item.Source) -ne $item.Entry.sha256) { throw 'File changed after preflight' }
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
[pscustomobject]@{ Action = $Action; Stage = $Stage; Verified = $pending.Count; Changed = $changed }
