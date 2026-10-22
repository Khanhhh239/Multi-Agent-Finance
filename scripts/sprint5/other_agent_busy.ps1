# Thoát 0 nếu hàng đợi sprint6 của agent kia còn chạy, 1 nếu đã xong. Dùng để nhường tài nguyên.
$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'sprint6[\\/]runner\.py' }
if ($p) { exit 0 } else { exit 1 }
