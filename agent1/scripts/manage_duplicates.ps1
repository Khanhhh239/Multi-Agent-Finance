[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('T0', 'UnifiedV2', 'Research', 'Small')]
    [string]$Dataset,
    [ValidateSet('Verify', 'Compact', 'Restore')]
    [string]$Action = 'Verify',
    [ValidateSet('All', '8', '9', '10', '11', '12', '13', '14')]
    [string]$Stage = 'All',
    [string]$RelativePath = ''
)

# Each dataset retains its original manifest, scope and recovery suffix.
# Verify is read-only; Compact/Restore preflight every selected file first.
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'archive_common.psm1') -Force
$profiles = @{
    T0 = @{
        Manifest = 't0_staging_cleanup_20261105.json'
        Method = 'hardlink_t0_payloads_and_remove_disposable_staging'
        Count = 186; Stages = @(); Backup = '.dedup-backup'
    }
    UnifiedV2 = @{
        Manifest = 'unified_v2_hardlink_dedup_20261105.json'
        Method = 'hardlink_to_r3'
        Count = 108; Stages = @(); Backup = '.dedup-backup'
    }
    Research = @{
        Manifest = 'research_hardlink_dedup_20261105.json'
        Method = 'hardlink_research_stages_8_9_10'
        Count = 333; Stages = @('8', '9', '10'); Backup = '.research-dedup-backup'
    }
    Small = @{
        Manifest = 'small_hardlink_dedup_20261105.json'
        Method = 'hardlink_small_stages_11_12_13_14'
        Count = 1641; Stages = @('11', '12', '13', '14'); Backup = '.small-dedup-backup'
    }
}
$datasetProfile = $profiles[$Dataset]
if ($Stage -ne 'All' -and $Stage -notin $datasetProfile.Stages) {
    throw "Stage $Stage does not belong to dataset $Dataset"
}

function Test-Scope([string]$Relative, [string]$EntryStage) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or $Relative.Contains('\') -or
        $Relative -match '(^|/)[.]{1,2}(/|$)') { return $false }
    if ($Dataset -eq 'T0') {
        return $Relative.StartsWith('data/T0/processed/', [StringComparison]::Ordinal)
    }
    switch ($EntryStage) {
        '8' { return $Relative -cmatch '^data/synthetic/(hc_|v3_candidate|v3_releasecheck|v[456]_lifecycle_control)[^/]+/[^/]+[.]parquet$' }
        '9' { return $Relative -cmatch '^data/T1/raw/(adjacent_source_research|late_only_augmentation)/' }
        '10' { return $Relative.StartsWith('outputs/', [StringComparison]::Ordinal) -and -not $Relative.StartsWith('outputs/maintenance/', [StringComparison]::Ordinal) }
        '11' { return $Relative -cmatch '^data/T0/processed/.+[.](json|jsonl|csv|parquet)$' }
        '12' { return $Relative -cmatch '^data/synthetic/[^/]+/[^/]+[.]parquet$' }
        '13' { return $Relative.StartsWith('outputs/', [StringComparison]::Ordinal) -and -not $Relative.StartsWith('outputs/maintenance/', [StringComparison]::Ordinal) }
        '14' { return $Relative.StartsWith('data/T1/raw/', [StringComparison]::Ordinal) }
    }
    return $false
}

$manifestPath = Get-SafePath ('outputs/maintenance/' + $datasetProfile.Manifest)
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$allEntries = @($manifest.duplicate_payloads)
if ($manifest.method -ne $datasetProfile.Method -or $allEntries.Count -ne $datasetProfile.Count) {
    throw "Unexpected $Dataset compaction manifest"
}
$destinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$sources = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $allEntries) {
    if ($Dataset -eq 'UnifiedV2') {
        $prefixes = @('outputs/data/unified_collection_v2_20261104/', 'outputs/data/unified_collection_v2_20261104_r2/')
        $prefix = @($prefixes | Where-Object { $entry.path.StartsWith($_, [StringComparison]::Ordinal) })
        if ($prefix.Count -ne 1) { throw "Unexpected duplicate path: $($entry.path)" }
        $suffix = $entry.path.Substring($prefix[0].Length)
        if ($suffix -match '(^|/)[.]{1,2}(/|$)' -or $suffix.Contains('\') -or
            $entry.retained_path -cne ('outputs/data/unified_collection_v2_20261104_r3/' + $suffix)) {
            throw "Invalid duplicate mapping: $($entry.path)"
        }
    } else {
        $entryStage = [string]$entry.stage
        if (($datasetProfile.Stages.Count -gt 0 -and $entryStage -notin $datasetProfile.Stages) -or
            -not (Test-Scope $entry.path $entryStage) -or
            -not (Test-Scope $entry.retained_path $entryStage)) {
            throw "Unexpected payload scope: $($entry.path)"
        }
    }
    if (-not $destinations.Add($entry.path) -or $entry.path -eq $entry.retained_path -or
        $entry.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $null -eq $entry.bytes -or $entry.bytes -lt 1 -or
        ($Dataset -eq 'Research' -and $entry.bytes -lt 65536) -or
        ($Dataset -eq 'Small' -and $entry.bytes -ge 65536)) {
        throw "Invalid duplicate mapping: $($entry.path)"
    }
    [void]$sources.Add($entry.retained_path)
}
foreach ($source in $sources) {
    if ($destinations.Contains($source)) { throw 'Retained source is also a replacement destination' }
}
$entries = $allEntries
if ($Stage -ne 'All') { $entries = @($entries | Where-Object { [string]$_.stage -eq $Stage }) }
if ($RelativePath) {
    $entries = @($entries | Where-Object { $_.path -ceq $RelativePath })
    if ($entries.Count -ne 1) { throw 'RelativePath must match exactly one entry within the selected stage' }
}

$pending = @(foreach ($entry in $entries) {
    $destination = Get-SafePath $entry.path
    $source = Get-SafePath $entry.retained_path
    $backup = Get-SafePath ($entry.path + $datasetProfile.Backup)
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
                Set-ArchiveMetadata $item.Destination $item.Entry
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
        if (($changed % 100) -eq 0) { Write-Verbose "Completed $changed / $($pending.Count) file operations" }
    }
}
[pscustomobject]@{ Dataset = $Dataset; Action = $Action; Stage = $Stage; Verified = $pending.Count; Changed = $changed }
