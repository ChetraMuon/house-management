# Run & Host Guide

This guide assumes the project is in `D:\house-management` on Windows.

The whole app is **one process**: FastAPI serves both the API and the built React site on
port **8000**. The database is SQLite (`backend/house_management.db`) and product images live in
`backend/uploads/products`.

---

## 1. Run it locally (one command)

```powershell
cd D:\house-management
.\deploy.ps1
```

What it does:

1. builds the React frontend into `frontend/dist`;
2. creates `backend/.venv` and installs Python packages if missing;
3. copies `backend/.env.example` to `backend/.env` on the first run;
4. starts the server on port **8000**.

Open **http://127.0.0.1:8000**.

Stop it with `Ctrl+C` in that window, or from another terminal:

```powershell
.\stop.ps1
```

### First-time configuration

Edit `backend/.env` before the first real use:

```dotenv
SECRET_KEY=<long random string>
SEED_MANAGER_PASSWORD=<strong password>
DATABASE_URL=sqlite:///./house_management.db
LOG_RETENTION_DAYS=7
```

`SEED_MANAGER_PASSWORD` only creates the manager if no manager exists. Change the password after
logging in. Never commit `backend/.env` (it is already git-ignored).

### Phones on the same Wi-Fi

1. Find this PC's address: `ipconfig` → IPv4 Address (for example `172.16.6.150`).
2. Allow the port once, in an **Administrator** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "House Management 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

3. Open `http://<that-ip>:8000` on the phone.

---

## 2. Temporary public link (free, no account)

```powershell
.\public.ps1
```

The script downloads `cloudflared` if needed and prints a `https://*.trycloudflare.com` address.
Keep the window open and the PC awake.

- The URL **changes every time** cloudflared restarts.
- No uptime guarantee — fine for demos, not for real card payments.
- Close the window to end public access.

The app must already be running (`.\deploy.ps1`) before starting the tunnel.

---

## 3. Permanent hosting on Railway (recommended)

This puts the app and its data in the cloud with a stable HTTPS address, so your PC can be off.

Requirements: a Railway account, and a payment method (the Hobby plan is about **$5/month**;
persistent volumes are not on the free trial).

The repository already contains everything Railway needs:

- `Dockerfile` — builds React + FastAPI into one container
- `docker-entrypoint.sh` — prepares the `/data` volume
- `railway.json` — health check `/health`, restart on failure

### Step by step

```powershell
cd D:\house-management

# 1. Install the CLI once (Node.js required)
npm install -g @railway/cli

# 2. Sign in (opens the browser)
railway login

# 3. Create and link a project
railway init --name house-management

# 4. Build and deploy the container
railway up -y

# 5. Add the persistent volume mounted at /data
railway volume add --mount-path /data

# 6. Point the app at the volume (four slashes = absolute path)
railway variable set DATABASE_URL=sqlite:////data/house_management.db --skip-deploys
railway variable set PRODUCT_IMAGE_DIR=/data/uploads/products --skip-deploys
railway variable set LOG_RETENTION_DAYS=7 --skip-deploys
railway variable set SECRET_KEY=<long-random-string> --skip-deploys
railway variable set SEED_MANAGER_PASSWORD=<strong-password> --skip-deploys

# 7. Create the public HTTPS address
railway domain --port 8000
```

Open the printed `https://*.up.railway.app` address. If the dashboard asks for a target port,
set **8000**.

### Copy the existing store data to the cloud

Run these once, after the volume exists and the first deployment has finished:

```powershell
# Database
railway volume files upload backend\house_management.db /house_management.db --overwrite

# Product images
Get-ChildItem backend\uploads\products\* | ForEach-Object {
    railway volume files upload $_.FullName "/uploads/products/$($_.Name)" --overwrite
}

# Restart so the app opens the uploaded database
railway redeploy -y
```

Log in with your existing account. Then change the manager password under **Change password**.

### Day-to-day

| Task | Command |
|---|---|
| Deploy new code | `railway up -y` |
| View logs | `railway logs` |
| Project status | `railway status` |
| Redeploy without changes | `railway redeploy -y` |
| Download a cloud backup of the DB | `railway volume files download /house_management.db .\backup-house_management.db` |

### PayWay (optional)

Add these as Railway variables when you are ready for QR payments:

```
PAYWAY_ENABLED=true
PAYWAY_MERCHANT_ID=...
PAYWAY_API_KEY=...
PAYWAY_BASE_URL=https://checkout.payway.com.kh
PAYWAY_CALLBACK_URL=https://<your-railway-domain>/api/payments/payway/webhook
PAYWAY_QR_LIFETIME_MINUTES=10
```

Then `railway redeploy -y`. Use **sandbox** credentials and
`https://checkout-sandbox.payway.com.kh` until PayWay gives you production keys.

---

## 4. Updating the app

Local:

```powershell
.\stop.ps1
.\deploy.ps1          # rebuilds the frontend and restarts
```

Cloud:

```powershell
railway up -y
```

---

## 5. Backups

- Local database: copy `backend\house_management.db` while the app is stopped.
- Local images: copy `backend\uploads\products`.
- Cloud database: `railway volume files download /house_management.db .\backup.db`
- Cloud images: `railway volume files download /uploads/products/<file> .\<file>`

Keep at least one copy on another disk or cloud drive.

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `Port 8000 is already in use` | Run `.\stop.ps1`, then `.\deploy.ps1` |
| Page loads but API errors | Check the backend window/log; restart with `.\deploy.ps1` |
| Public URL stopped working | The quick tunnel ended. Run `.\public.ps1` again; the URL will change |
| Cloud app is down | `railway logs`, then `railway redeploy -y` |
| Cloud login fails after a redeploy | The volume is not mounted at `/data`, or `DATABASE_URL` is not `sqlite:////data/house_management.db` |
| Phone cannot connect | Same Wi-Fi? Firewall rule added? Use the PC's current IPv4 address |

Logs on this PC (when started by the automation):

- `%TEMP%\opencode\backend-out.log`
- `%TEMP%\opencode\backend-err.log`

---

## 7. Security checklist

- Change the seeded manager password immediately.
- Keep `backend/.env`, the database, and product images out of Git.
- Use HTTPS (Railway provides it) before enabling PayWay.
- Rotate any PayWay key that was shared in chat or stored in an old image.
- Give each employee their own account; deactivate leavers in **Users**.
