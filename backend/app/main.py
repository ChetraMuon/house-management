import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import database, models
from .config import settings
from .database import init_db
from .deps import client_info
from .retention import purge_expired_logs, retention_loop
from .routers import (
    approvals,
    auth,
    customers,
    logs,
    payments,
    products,
    reports,
    sales,
    simulator,
    stock,
    users,
)
from .security import decode_token
from .seed import ensure_seed_manager

logger = logging.getLogger("house.audit")
app = FastAPI(title="House Management System", version="1.0.0")

AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# These requests are either already tracked as sign-in events, are read-only
# previews, or arrive from PayWay rather than from a signed-in user.
AUDIT_SKIP_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/sales/change",
    "/api/payments/payway/webhook",
}
product_image_dir = Path(settings.PRODUCT_IMAGE_DIR).resolve()
product_image_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads/products",
    StaticFiles(directory=str(product_image_dir)),
    name="product-images",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _write_request_audit(request: Request, status_code: int) -> None:
    """Record any authenticated state-changing request that a router did not
    already audit. This keeps the audit trail complete for every user action."""
    try:
        path = request.url.path
        if request.method not in AUDIT_METHODS or not path.startswith("/api/"):
            return
        if path in AUDIT_SKIP_PATHS:
            return
        if getattr(request.state, "audit_recorded", False):
            return

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return
        try:
            user_id = int(decode_token(token)["sub"])
        except Exception:
            return

        with database.SessionLocal() as db:
            user = db.get(models.User, user_id)
            if user is None:
                return
            ip, _ = client_info(request)
            parts = [part for part in path.split("/") if part]
            entity = parts[1] if len(parts) > 1 else "api"
            action = f"{request.method} {path.removeprefix('/api')}"[:60]
            db.add(models.AuditLog(
                actor_id=user.id,
                username=user.username,
                ip_address=ip,
                action=action,
                entity=entity[:40],
                detail=f"status={status_code}",
            ))
            db.commit()
    except Exception:
        logger.exception("Could not record request audit entry")


@app.middleware("http")
async def audit_requests(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        _write_request_audit(request, 500)
        raise
    _write_request_audit(request, response.status_code)
    return response


@app.on_event("startup")
async def startup() -> None:
    init_db()
    with database.SessionLocal() as db:
        ensure_seed_manager(db)
        purge_expired_logs(db)
    app.state.retention_task = asyncio.create_task(retention_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "retention_task", None)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


for r in (auth, users, products, stock, sales, approvals, reports, logs, customers, payments, simulator):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/health", include_in_schema=False)
def health_alias():
    """Health endpoint for reverse proxies and hosting platforms."""
    return {"status": "ok"}


# Serve the production React build from the same origin when it exists.
# Development still uses Vite on 5173, which proxies /api to this server.
def _frontend_dist() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "frontend" / "dist",  # repo checkout: <root>/frontend/dist
        here.parents[1] / "frontend" / "dist",  # container: /srv/frontend/dist
        Path.cwd() / "frontend" / "dist",
    ]
    return next((path for path in candidates if path.is_dir()), candidates[0])


frontend_dist = _frontend_dist()
if frontend_dist.is_dir():
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        if full_path == "uploads" or full_path.startswith("uploads/"):
            raise HTTPException(404, "Not found")
        target = (frontend_dist / full_path).resolve()
        if target.is_file() and target.is_relative_to(frontend_dist):
            return FileResponse(target)
        return FileResponse(frontend_dist / "index.html", headers={"Cache-Control": "no-cache"})
