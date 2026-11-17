# House Management - native deployment script (Windows)
# Builds the React app and serves it together with the FastAPI API on port 8000.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$listener = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Where-Object { $_.RemotePort -eq 0 } | Select-Object -First 1
if ($listener) {
    throw "Port 8000 is already in use. Run .\stop.ps1 (or press Ctrl+C in the deploy window) and try again."
}

Write-Host "==> Building frontend" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
try {
    if (-not (Test-Path "node_modules")) {
        npm ci
    }
    npm run build
} finally {
    Pop-Location
}

Write-Host "==> Preparing backend" -ForegroundColor Cyan
Push-Location (Join-Path $root "backend")
try {
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }
    & ".\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created backend/.env from .env.example - edit it before going live." -ForegroundColor Yellow
    }

    Write-Host "==> Starting app on http://0.0.0.0:8000" -ForegroundColor Green
    Write-Host "    Local: http://127.0.0.1:8000"
    & ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
} finally {
    Pop-Location
}
