# House Management - temporary public HTTPS tunnel (Cloudflare quick tunnel).
# The app must already be running on http://127.0.0.1:8000 (run .\deploy.ps1 first).
$ErrorActionPreference = "Stop"

$cloudflared = Join-Path $env:TEMP "opencode\cloudflared.exe"
if (-not (Test-Path $cloudflared)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $cloudflared) | Out-Null
    Write-Host "==> Downloading cloudflared" -ForegroundColor Cyan
    Invoke-WebRequest `
        -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $cloudflared `
        -UseBasicParsing
}

try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
    if ($health.StatusCode -ne 200) { throw "health check failed" }
} catch {
    throw "The app is not running on port 8000. Start it with .\deploy.ps1 first."
}

Write-Host "==> Starting temporary public tunnel (auto-restart enabled)" -ForegroundColor Green
Write-Host "    Press Ctrl+C to close public access."
while ($true) {
    & $cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate `
        --protocol http2 --edge-ip-version 4 --retries 10
    Write-Host "==> Tunnel stopped; restarting in 5 seconds (press Ctrl+C to quit)." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
