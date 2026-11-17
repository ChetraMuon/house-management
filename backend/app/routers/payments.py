"""Payment gateway configuration and callbacks."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, payway, schemas
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from .sales import _sync_payway_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/config", response_model=schemas.PaywayConfigOut)
def payment_config(_: models.User = Depends(get_current_user)):
    """Feature flags the checkout screen needs (no secrets)."""
    return {
        "payway_enabled": payway.enabled(),
        "currency": settings.PAYWAY_CURRENCY.upper(),
        "sandbox": payway.is_sandbox(),
        "simulator_enabled": payway.simulator_available(),
    }


@router.post("/payway/webhook", summary="ABA PayWay payment callback")
async def payway_webhook(request: Request, db: Session = Depends(get_db)):
    """PayWay pushback. The body is never trusted on its own: the status is
    re-checked against PayWay's API before a sale is marked paid."""
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON")

    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid payload")

    reference = payload.get("merchant_ref") or payload.get("tran_id")
    if not reference:
        return {"status": "ignored", "reason": "missing transaction reference"}

    payment = db.scalar(
        select(models.Payment).where(models.Payment.provider_txn_id == str(reference))
    )
    if payment is None or payment.provider != "PAYWAY":
        return {"status": "ignored", "reason": "unknown transaction"}

    sale = db.get(models.Sale, payment.sale_id)
    user = db.get(models.User, payment.received_by)
    if sale is None or user is None:
        return {"status": "ignored", "reason": "missing sale or cashier"}

    try:
        # Force a fresh check: the payment may be locally cancelled/expired
        # even though the customer paid just before the QR was closed.
        state = _sync_payway_payment(db, sale, payment, user, force=True)
    except payway.PaywayError as exc:
        # Ask PayWay to retry the callback rather than accepting an
        # unverified "paid" notification.
        raise HTTPException(502, f"Could not verify PayWay payment: {exc.message}")

    return {"status": "ok", "payment_status": state}
