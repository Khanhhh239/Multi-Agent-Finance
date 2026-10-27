# Thoát 0 nếu tiến trình còn chạy, 1 nếu đã xong, 2 nếu không kiểm được.
param([string]$Pattern = 'sprint6[\\/]runner\.py')
try {
    $p = Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.CommandLine -match $Pattern }
} catch {
    Write-Error "Cannot inspect process queue: $($_.Exception.Message)"
    exit 2
}
if ($p) { exit 0 } else { exit 1 }
