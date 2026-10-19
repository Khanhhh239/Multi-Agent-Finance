param([int]$Port=11435)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$artifactRoot=Join-Path $taskRoot 'artifacts'
New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
$listening=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) { throw "Port $Port already in use; inspect the existing server before starting another." }
$env:OLLAMA_HOST="127.0.0.1:$Port"
$env:OLLAMA_KV_CACHE_TYPE='q8_0'
$env:OLLAMA_FLASH_ATTENTION='1'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$env:OLLAMA_NO_CLOUD='1'
$env:LLAMA_ARG_CACHE_RAM='0'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$server=Start-Process -FilePath (Get-Command ollama.exe).Source -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $artifactRoot "p2-ollama-$stamp.err.log") -RedirectStandardOutput (Join-Path $artifactRoot "p2-ollama-$stamp.out.log")
$server.Id | Set-Content (Join-Path $artifactRoot 'p2-ollama.pid')
@{ report_notice='formulas not accountant-approved'; port=$Port; pid=$server.Id; KV='q8_0'; flash_attention=$true; parallel=1; max_loaded=1; prompt_cache_ram_mib=0; started=$stamp } | ConvertTo-Json | Set-Content (Join-Path $artifactRoot "p2-server-$stamp.json")
Write-Output "Started dedicated experimental Ollama PID $($server.Id), port $Port. Check health before measuring."
