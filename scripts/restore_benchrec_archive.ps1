[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Verify', 'Restore')]
    [string]$Action = 'Verify',
    [string]$Name = ''
)

$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char[]]'\/')
$workspacePrefix = $workspacePath + [IO.Path]::DirectorySeparatorChar
$archivePrefix = 'data/T0/raw/benchrec_kaggle/2026-10-19-v3/'
$allowedNames = @('BenchRec_cash_v1.0_eval.csv', 'BenchRec_cash_v1.0_solution.csv', 'BenchRec_cash_v1.0_train.csv', 'MatcherByChatGPT_submission.csv')

function Get-SafePath([string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) { throw 'Invalid relative path' }
    $full = [IO.Path]::GetFullPath((Join-Path $workspacePath $Relative))
    if (-not $full.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Path leaves workspace: $Relative" }
    $ancestor = $full
    while ($ancestor -ne $workspacePath) {
        if (Test-Path -LiteralPath $ancestor) {
            if (((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked path rejected: $Relative" }
        }
        $ancestor = Split-Path -Path $ancestor -Parent
    }
    return $full
}
function Get-Digest([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Get-StreamDigest([IO.Stream]$Stream) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToHexString($algorithm.ComputeHash($Stream)).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

$manifest = Get-Content -LiteralPath (Get-SafePath 'outputs/maintenance/benchrec_zip_cleanup_20261106.json') -Raw | ConvertFrom-Json
if ($manifest.method -ne 'remove_extracted_csv_keep_verified_zip' -or @($manifest.archived_csv_files).Count -ne 4 -or
    $manifest.archive_path -ne ($archivePrefix + 'dataset.zip')) { throw 'Unexpected BenchRec archive manifest' }
$archivePath = Get-SafePath $manifest.archive_path
if ((Get-Digest $archivePath) -ne $manifest.archive_sha256) { throw 'Retained ZIP hash changed' }
$entries = @($manifest.archived_csv_files)
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $entries) {
    if ($entry.zip_member -cnotin $allowedNames -or $entry.path -cne ($archivePrefix + $entry.zip_member) -or
        -not $seen.Add($entry.path) -or $entry.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid archive mapping' }
}
if ($Name) {
    $entries = @($entries | Where-Object { $_.zip_member -ceq $Name })
    if ($entries.Count -ne 1) { throw 'Name must match one approved CSV filename' }
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    # Verify every selected member and destination before writing anything.
    $pending = @(foreach ($entry in $entries) {
        $members = @($zip.Entries | Where-Object { $_.FullName -ceq $entry.zip_member })
        if ($members.Count -ne 1 -or $members[0].Length -ne $entry.bytes) { throw "ZIP member missing, duplicated or resized: $($entry.zip_member)" }
        $stream = $members[0].Open()
        try { if ((Get-StreamDigest $stream) -ne $entry.sha256) { throw "ZIP member hash mismatch: $($entry.zip_member)" } }
        finally { $stream.Dispose() }
        $destination = Get-SafePath $entry.path
        $temporary = Get-SafePath ($entry.path + '.restoring')
        if (Test-Path -LiteralPath $temporary) { throw "Restore temporary file already exists: $temporary" }
        $exists = Test-Path -LiteralPath $destination
        if ($exists -and (-not (Test-Path -LiteralPath $destination -PathType Leaf) -or (Get-Digest $destination) -ne $entry.sha256)) {
            throw "Destination contains different data; refusing overwrite: $destination"
        }
        [pscustomobject]@{ Entry=$entry; Member=$members[0]; Destination=$destination; Temporary=$temporary; Exists=$exists }
    })
    $restored = 0
    if ($Action -eq 'Restore') {
        foreach ($item in $pending) {
            if ($item.Exists -or -not $PSCmdlet.ShouldProcess($item.Destination, 'Restore verified CSV from retained ZIP')) { continue }
            $created = $false
            try {
                $output = [IO.File]::Open($item.Temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                $created = $true
                try {
                    $inputStream = $item.Member.Open()
                    try { $inputStream.CopyTo($output) } finally { $inputStream.Dispose() }
                } finally { $output.Dispose() }
                if ((Get-Digest $item.Temporary) -ne $item.Entry.sha256) { throw 'Restored CSV hash mismatch' }
                # Both absolute paths were validated within the workspace.
                Move-Item -LiteralPath $item.Temporary -Destination $item.Destination
                $created = $false
                $file = Get-Item -LiteralPath $item.Destination
                $file.CreationTimeUtc = [datetime]::Parse($item.Entry.original_creation_time_utc).ToUniversalTime()
                $file.LastWriteTimeUtc = [datetime]::Parse($item.Entry.original_last_write_time_utc).ToUniversalTime()
                $file.Attributes = [IO.FileAttributes][int]$item.Entry.original_attributes
                $restored++
            } finally {
                if ($created -and (Test-Path -LiteralPath $item.Temporary)) { Remove-Item -LiteralPath $item.Temporary -Force }
            }
        }
    }
    [pscustomobject]@{ Verified=$pending.Count; MissingCSV=@($pending | Where-Object { -not $_.Exists }).Count; Restored=$restored; Action=$Action }
} finally { $zip.Dispose() }
