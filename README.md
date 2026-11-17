# House Management System

FastAPI + React (Vite) POS for a houseware store. Three roles: **manager**, **admin**, **emp**.

The app runs natively with SQLite, or with Docker Compose (MySQL 8 + nginx).

## Deploy on Windows (native)

Requirements: Python 3.10+ and Node.js 18+.

```powershell
cd D:\house-management
.\deploy.ps1
```

`deploy.ps1`:

1. builds the React app into `frontend/dist`;
2. creates `backend/.venv` and installs requirements if they are missing;
3. copies `backend/.env.example` to `backend/.env` on first run;
4. starts FastAPI on port **8000**.

FastAPI serves both the API and the built React SPA, so there is only one process to run.

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000 | App (local) |
| http://<server-ip>:8000 | App (LAN — allow port 8000 in Windows Firewall) |
| http://127.0.0.1:8000/health | Health check |
| http://127.0.0.1:8000/docs | Swagger API docs |

Before the first start, edit `backend/.env` and set at least:

```dotenv
SECRET_KEY=<long random value>
SEED_MANAGER_PASSWORD=<strong password>
DATABASE_URL=sqlite:///./house_management.db
```

Active demo accounts on this machine:

| Role | Username |
|---|---|
| manager | `manager` |
| admin | `admin01` |
| emp | `cashier` |

Passwords were rotated before public exposure; the current values are in the deployment handover.
Change them after first login. Unused test accounts were deactivated.

To stop the app, run `.\stop.ps1` (or press `Ctrl+C` in the deploy window). If port 8000 is
already in use, stop the old `uvicorn` process first, then run `.\deploy.ps1` again.

## Public access (temporary tunnel)

The app can be exposed through a temporary Cloudflare HTTPS URL:

```powershell
.\public.ps1
```

The script downloads `cloudflared` to `%TEMP%\opencode` if needed and prints a
`https://*.trycloudflare.com` URL. Keep the window open and the PC awake. Quick tunnels are
ephemeral: the URL changes on restart and has no uptime guarantee.

For a permanent public deployment, use a named Cloudflare Tunnel with your own domain, or host
the Docker setup on a VPS with HTTPS. Do not use a quick tunnel for production card payments.

### Manual native run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env      # edit SECRET_KEY, SEED_MANAGER_PASSWORD, PayWay keys
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The frontend must be built once with `cd frontend; npm ci; npm run build`.

### Frontend development

```powershell
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

Vite proxies `/api` and `/uploads` to `http://127.0.0.1:8000`. Set
`VITE_PROXY_TARGET` to point at a different backend.

## Docker deployment

Docker is optional; the native deployment above is the one running on this machine.

```powershell
Copy-Item deploy.env.example .env
# edit .env: SECRET_KEY, MySQL passwords, manager password, PayWay credentials
docker compose up --build -d
```

- App: http://localhost:5173
- API docs: http://localhost:8000/docs
- MySQL data and product images persist in the `dbdata` and `product_uploads` volumes.
- Stop: `docker compose down` (data is kept). Wipe data: `docker compose down -v`.

Docker files: `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`,
`docker-compose.yml`, `deploy.env.example`. Nginx serves the SPA and proxies `/api`,
`/uploads`, and `/health` to the backend container.

## Who can do what

| Feature | manager | admin | emp |
|---|:-:|:-:|:-:|
| Create employee accounts | ✅ | | |
| Change role emp ⇄ admin, deactivate user | ✅ | | |
| Add / edit / archive products, categories | ✅ | | |
| Stock IN / OUT | ✅ | ✅ | |
| Stock adjust (set exact qty) | ✅ | | |
| Approve / reject sale **over $10,000** | | ✅ | |
| Track approvals (who approved what) | ✅ | ✅ (view) | |
| Check employee sales by day (receipt, customer name & phone) | ✅ | ✅ | |
| Complete sandbox PayWay test payments (ABA Simulator) | ✅ | ✅ | |
| Track sign-ins and audit trail, filter/delete logs by date | ✅ | | |
| View & generate reports (all staff), CSV, stock report | ✅ | ✅ (view) | |
| Checkout, cash input, change calculation, print receipt | | | ✅ |
| Daily report + report range (own sales only), print | | | ✅ |

## Product images

Managers can add or replace an image in **Products** when creating or editing a catalog item.
Employees see the image on each product card in **New sale**. PNG, JPEG, GIF, and WebP files up
to 5 MB are supported. Images are stored under `backend/uploads/products` for a manual backend
run; Docker Compose keeps them in the persistent `product_uploads` volume.

For production, persist `PRODUCT_IMAGE_DIR` and proxy `/uploads/products/` requests to the backend,
alongside the existing `/api` proxy.

## Product deletion and archive

- **Delete** is shown only when a product can be removed safely: stock is `0` and the product
  has no sale items or stock movements.
- Products with stock or sales/stock history show **Archive** instead. Archiving sets
  `is_active = false`, hides the item from checkout and active listings, and keeps all history.
- Tick **Show archived** on the Products page to see archived items and use **Restore**.
- `DELETE /api/products/{id}` returns `409` for a product that cannot be hard-deleted. Archive
  it with `PATCH /api/products/{id}` and `{"is_active": false}`.

## Stock quick update

Managers and admins can open **Stock**, then click a product name (or its **Stock in** /
**Stock out** button) to record a movement without using the form at the top. The dialog shows
the current balance and the balance after the change. Stock out cannot exceed the quantity on
hand. The top form remains available for stock in, stock out, and manager-only exact
adjustments; its product field searches by name or SKU.

## Employee sales

**Employee sales** does not load automatically. Choose a day and optionally an employee
(defaults to **All employees**), then select **Show sales**. The **Today** button filters
today's sales immediately. Changing a filter clears the current results so every search is
explicit. The employee choices come from
`GET /api/sales/employee-sales/employees` (managers and admins only).

## Logs, audit trail, and retention

**Activity & audit** has two tabs:

- **Sign-ins** records every login, logout, and failed login with the username, IP address,
  device/user agent, and time.
- **Audit trail** records every state-changing user action (create, update, archive, delete,
  stock movement, checkout, payment, approval, password change, log deletion, and so on). Each
  row shows the actor's username and ID, IP address, action, entity, and detail.

All authenticated `POST`, `PUT`, `PATCH`, and `DELETE` API calls are captured automatically.
Routers with richer audit entries (products, users, approvals, password changes, sandbox
payments, and log deletion) write those entries instead, so an action is not recorded twice.
Login/logout are tracked in the sign-in log, and the read-only change preview and PayWay webhook
are excluded. When the app runs behind Cloudflare or another proxy, the real client IP is read
from `CF-Connecting-IP` or `X-Forwarded-For`.

Both tabs support **From** / **To** date filters (inclusive, interpreted in the server's local
timezone) and a **Reset** button. Sign-ins can also be filtered by event; the audit trail can be
filtered by username. Managers can:

- **Delete selected dates** — removes only the current tab's records inside the selected range.
- **Clear all sign-ins** / **Clear all audit entries** — removes every record in that tab.

Every deletion is written to the audit trail with the manager's username, IP address, deleted
count, and date range. Clearing the audit trail leaves one `AUDIT_LOGS_CLEARED` entry as
evidence of who performed the deletion.

**Retention:** sign-in and audit rows older than `LOG_RETENTION_DAYS` (default `7`) are deleted
automatically. Cleanup runs at startup, before each log query, and once an hour in the background.
Set the value in `backend/.env` (or the deployment environment) if a different retention period is
needed.

## Checkout flow

1. **emp** builds a cart → `POST /api/sales`
   - total ≤ `$10,000` → status `READY`
   - total > `$10,000` → status `PENDING_APPROVAL` and a row in `approvals`
2. **admin** opens *Approvals* → approve or reject (with a note). Approved → `APPROVED`.
3. **emp** opens *My Sales* → **Checkout**. The server refuses checkout for a sale that still needs approval.
4. Cash: emp types the money received. The server computes the **change** and a bill/coin
   breakdown; checkout is blocked if the money is short.
5. In one DB transaction: product rows are locked (`SELECT … FOR UPDATE`), stock is deducted,
   `stock_movements` (type `SALE`) and `payments` rows are written, sale becomes `PAID`.
6. **Print receipt** (80 mm thermal friendly) from the browser print dialog.

The threshold lives in the `settings` table (`approval_threshold`) so it can be changed without code.
Currency is shown as USD — change `money()` in `frontend/src/api.js` and `DENOMINATIONS` in `backend/app/money.py` for another currency.

## ABA PayWay QR payments (optional)

The checkout screen can show a dynamic **ABA KHQR** and confirm the sale automatically.
Cash and manual card/transfer keep working exactly as before; PayWay is only enabled when configured.

1. Register a sandbox merchant at <https://sandbox.payway.com.kh/register-sandbox/> and wait for the
   credentials email. Ask PayWay to whitelist your server domain/IP.
2. Add the credentials to `backend/.env` (or the Docker `.env`):

   ```dotenv
   PAYWAY_ENABLED=true
   PAYWAY_MERCHANT_ID=your_merchant_id
   PAYWAY_API_KEY=your_payway_public_key
   PAYWAY_BASE_URL=https://checkout-sandbox.payway.com.kh
   PAYWAY_CALLBACK_URL=https://your-domain.com/api/payments/payway/webhook
   PAYWAY_QR_LIFETIME_MINUTES=30
   PAYWAY_CURRENCY=USD
   # Built-in test payer; only works while PAYWAY_BASE_URL is the sandbox.
   PAYWAY_SIMULATOR_ENABLED=true
   ```

   For this QR integration, set `PAYWAY_API_KEY` to the short **Public Key** value from the email.
   The RSA keys and the `/payments/purchase` URL are for a different integration flow and are not
   used to create these dynamic QR payments. Keep all credentials out of source control. If they
   have been shared publicly, ask PayWay to rotate them before enabling payments.

   `PAYWAY_CALLBACK_URL` is optional. The POS also polls PayWay's status API, so local development
   works without a public webhook. In production, set it to the public HTTPS URL above.
3. Restart the backend. In employee checkout, choosing **Transfer (ABA QR)** creates a dynamic QR;
   **Manual transfer** remains available for transfers recorded without PayWay.
4. In production, scan the QR with ABA Mobile or any KHQR banking app. The sale flips to
   `PAID` as soon as the backend verifies the payment with PayWay, and the receipt prints normally.

**Sandbox limitation:** a QR created with sandbox credentials cannot be paid by the production
ABA Mobile app. Use the built-in **ABA Simulator** scanner (below) or ABA's official
**ABA Simulator** iOS app (TestFlight: <https://testflight.apple.com/join/HNyq7UCm>). To accept
real customer payments, apply for production PayWay credentials, set
`PAYWAY_BASE_URL=https://checkout.payway.com.kh`, and expose the webhook over public HTTPS.

### Built-in ABA sandbox simulator

The app includes a web-based test payer so you can scan and complete a sandbox QR without ABA's
official TestFlight app. It is deliberately limited to sandbox mode:

- It only appears for **manager** and **admin** users under **Operations → ABA Simulator**.
- It is only available when `PAYWAY_SIMULATOR_ENABLED=true` **and**
  `PAYWAY_BASE_URL` contains `sandbox`.
- It marks the pending QR as paid in this POS, records `provider_ref=SIMULATED`, and writes a
  `PAYWAY_SIMULATED` audit entry. **No real money moves and no ABA account is charged.**
- It disappears automatically when you switch to production PayWay credentials.

Usage:

1. As an employee, create a sale and choose **Transfer (ABA QR)** on the checkout screen.
   The POS creates the PayWay payment request and displays the QR.
2. As a manager or admin, open **Operations → ABA Simulator** on a phone (iPhone Safari works).
3. Tap **Scan QR code**, allow camera access, and point the phone at the POS screen. The scanner
   reads the KHQR (including PayWay's styled QR with a centre logo) and finds the matching pending
   payment request.
4. Confirm **Approve test payment**. The sale becomes `PAID`, the checkout confirms automatically,
   the Telegram alert is sent, and the receipt can be printed.

If Safari says the camera permission was denied, check **Settings → Safari → Camera → Allow** and
reload the page, or open the site directly in Safari/Chrome instead of an in-app browser. You can
also tap **Upload QR photo** (take a photo of the POS screen first), type the short reference
printed under the QR (for example `S94ad12f1d1`), or pick the receipt from the pending list.

The simulator never trusts a browser-supplied amount or status: the backend loads the pending
payment from the database, checks that it is still pending and unexpired, and reuses the normal
PayWay finalisation path. Keep it disabled in production.

Stock is reserved when the QR is created and restored if the QR is cancelled, declined, or expires.
The webhook body is never trusted by itself: the backend re-checks every callback against PayWay's
`check-transaction-2` API before marking a sale paid.

## Database tables

`users`, `settings`, `categories`, `products`, `stock_movements`, `sales`, `sale_items`,
`payments`, `approvals`, `login_logs`, `audit_logs` — see `database/schema.sql`.

```
users ─┬─< sales ─┬─< sale_items >─ products ─< stock_movements
       │          ├── payments (1:1)
       │          └── approvals (1:1, only for sales over the limit)
       ├─< login_logs
       └─< audit_logs
categories ─< products
```

## Project layout

```
database/schema.sql          full MySQL schema + seed data
backend/app/                 main.py, models.py, schemas.py, security.py, deps.py, money.py, payway.py, seed.py
backend/app/routers/         auth, users, products, stock, sales, approvals, reports, logs, payments, simulator
backend/tests/               unit tests (money / change calculation / PayWay / simulator / permissions)
frontend/src/pages/          Login, Checkout, Sales, Approvals, Stock, Products, Reports, Users, Logs, Customers, EmployeeSales, PaywaySimulator
frontend/src/components/     PaymentPanel (cash + PayWay QR), PaywayQr, Receipt (print)
deploy.ps1                   native Windows build + start
stop.ps1                     stop the native app on port 8000
public.ps1                   temporary public HTTPS tunnel
docker-compose.yml           MySQL + backend + nginx frontend
```

## Production notes

- Set a long random `SECRET_KEY`; serve behind HTTPS and set `CORS_ORIGINS` to the real origin.
- Change the seeded manager password and the demo cashier password before exposing the app.
- Rotate any PayWay key that has been pasted into chat or committed to git.
- Back up the SQLite file (`backend/house_management.db`) and `backend/uploads/` regularly.
  For multiple concurrent stores or servers, use the Docker/MySQL deployment instead.
- Keep `.env` files, the database, uploads, and build output out of git — see `.gitignore`.
