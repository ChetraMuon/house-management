"""Sandbox-only ABA PayWay test payer.

The official ABA Simulator is a separate mobile app. This router provides the
same "approve a pending sandbox QR" action inside the POS so a sale can be
completed end to end without real money. It is never exposed when PayWay is
configured for production.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, payway, schemas
from ..config import settings
from ..database import get_db
from ..deps import audit, require_roles
from .sales import _finalize_payway_sale, _safe_close_payway

router = APIRouter(prefix="/payway-simulator", tags=["payway-simulator"])
management = require_roles("manager", "admin")


def _require_simulator() -> None:
    if not payway.simulator_available():
        raise HTTPException(404, "The PayWay sandbox simulator is not available.")


def _simulator_row(sale: models.Sale, payment: models.Payment, now: datetime) -> dict:
    expires = payment.expires_at
    expired = bool(expires and now > expires)
    if expires and expires.tzinfo is None:
        # Match the QR endpoint: send the server's local offset so the browser
        # countdown is correct even when the POS runs in another timezone.
        expires = expires.astimezone()
    cashier = sale.cashier
    return {
        "sale_id": sale.id,
        "receipt_no": sale.receipt_no,
        "customer_name": sale.customer_name,
        "customer_phone": sale.customer_phone,
        "total": sale.total,
        "currency": settings.PAYWAY_CURRENCY.upper(),
        "tran_id": payment.provider_txn_id or "",
        "status": payment.status,
        "expires_at": expires,
        "created_at": sale.created_at,
        "cashier_name": (cashier.full_name or cashier.username) if cashier else "—",
        "expired": expired,
    }


@router.get("/pending", response_model=list[schemas.PaywaySimulatorSaleOut],
            summary="List pending sandbox PayWay QRs")
def pending_sales(
    db: Session = Depends(get_db),
    _: models.User = Depends(management),
):
    _require_simulator()
    now = datetime.now()
    sales = db.scalars(
        select(models.Sale)
        .join(models.Payment, models.Payment.sale_id == models.Sale.id)
        .options(
            selectinload(models.Sale.payment),
            selectinload(models.Sale.cashier),
            selectinload(models.Sale.customer),
        )
        .where(
            models.Payment.provider == "PAYWAY",
            models.Payment.status == "PENDING",
            models.Sale.status.in_(("READY", "APPROVED")),
        )
        .order_by(models.Sale.created_at.desc(), models.Sale.id.desc())
        .limit(100)
    ).all()
    return [_simulator_row(sale, sale.payment, now) for sale in sales]


@router.post("/{sale_id}/pay", response_model=schemas.PaywayStatusOut,
             summary="Mark a pending sandbox QR as paid")
def simulate_payment(
    sale_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(management),
):
    _require_simulator()
    sale = db.scalar(
        select(models.Sale)
        .options(
            selectinload(models.Sale.items),
            selectinload(models.Sale.payment),
            selectinload(models.Sale.approval),
            selectinload(models.Sale.customer),
        )
        .where(models.Sale.id == sale_id)
    )
    if sale is None:
        raise HTTPException(404, "Sale not found")

    payment = sale.payment
    if payment is None or payment.provider != "PAYWAY":
        raise HTTPException(404, "No PayWay payment found for this sale")

    if payment.status == "SUCCEEDED" or sale.status == "PAID":
        return {
            "sale_id": sale.id,
            "status": "SUCCEEDED",
            "sale_status": sale.status,
            "sale": sale,
            "message": "This sale is already paid.",
        }

    if sale.status == "PENDING_APPROVAL":
        raise HTTPException(403, "This sale still needs admin approval before payment.")
    if sale.status in ("REJECTED", "CANCELLED"):
        raise HTTPException(400, f"Sale is {sale.status.lower()} and cannot be paid.")
    if payment.status != "PENDING":
        raise HTTPException(400, f"This payment is already {payment.status.lower()}.")
    if payment.expires_at and datetime.now() > payment.expires_at:
        raise HTTPException(
            400,
            "This QR has expired. Ask the cashier to refresh the QR on the checkout screen.",
        )

    # Shape matches a PayWay check-transaction response so the normal sale
    # finalisation path can be reused (stock is already reserved by the QR).
    result = {
        "status": {"code": "00", "message": "Simulated sandbox payment"},
        "data": {
            "payment_status": "APPROVED",
            "payment_status_code": 0,
            "apv": "SIMULATED",
            "payment_amount": float(sale.total),
            "payment_currency": settings.PAYWAY_CURRENCY.upper(),
            "simulated": True,
        },
    }
    tran_id = payment.provider_txn_id
    _finalize_payway_sale(db, sale, payment, result, user)
    # The POS has recorded the payment; make the sandbox QR unpayable too.
    _safe_close_payway(tran_id)
    audit(
        db,
        user.id,
        "PAYWAY_SIMULATED",
        "sale",
        sale.id,
        detail=f"Simulated sandbox PayWay payment {tran_id} for {sale.receipt_no}",
        request=request,
        username=user.username,
    )
    db.commit()

    return {
        "sale_id": sale.id,
        "status": "SUCCEEDED",
        "sale_status": sale.status,
        "sale": sale,
        "message": "Simulated payment approved. No real money moved.",
    }
