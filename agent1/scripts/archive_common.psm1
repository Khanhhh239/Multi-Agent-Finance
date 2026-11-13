# Shared path and hash checks for maintenance tools. Paths stay inside agent1
# and may not traverse directory links, even when the leaf does not exist yet.
function Get-SafePath([string]$Relative) {
    $workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char[]]'\/')
    $workspacePrefix = $workspacePath + [IO.Path]::DirectorySeparatorChar
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) {
        throw 'Invalid relative path'
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
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Set-ArchiveMetadata([string]$Path, $Entry) {
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    # ConvertFrom-Json may return DateTime instead of a string. Casting directly
    # preserves its timezone; Parse(DateTime) first stringifies and loses it.
    $file.CreationTimeUtc = ([datetimeoffset]$Entry.original_creation_time_utc).UtcDateTime
    $file.LastWriteTimeUtc = ([datetimeoffset]$Entry.original_last_write_time_utc).UtcDateTime
    $file.Attributes = [IO.FileAttributes][int]$Entry.original_attributes
}

Export-ModuleMember -Function Get-SafePath, Get-Digest, Set-ArchiveMetadata
