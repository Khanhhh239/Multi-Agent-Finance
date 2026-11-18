# Starts the platform shell and all four agents via the unified launcher.
param([switch]$NoBrowser, [switch]$StopOnly)
& "$PSScriptRoot\run_web.ps1" @PSBoundParameters
