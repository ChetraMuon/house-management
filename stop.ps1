# House Management - stop the native deployment on port 8000.
$ErrorActionPreference = "Stop"

$listeners = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Where-Object { $_.RemotePort -eq 0 }
if (-not $listeners) {
    Write-Host "Nothing is listening on port 8000." -ForegroundColor Yellow
    exit 0
}

$processIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped $($process.ProcessName) (PID $processId)." -ForegroundColor Green
    }
}
