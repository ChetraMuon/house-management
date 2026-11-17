"""Sales / checkout.

Flow
  1. emp  POST /sales                -> order created
        total <= threshold : status READY
        total >  threshold : status PENDING_APPROVAL (+ approval row for an admin)
  2. admin approves (see approvals.py) -> status APPROVED
  3. emp  POST /sales/{id}/checkout  -> only allowed when READY or APPROVED.
        Locks stock rows, deducts stock, stores cash received + change, status PAID.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import models, payway, schemas
from ..config import settings as app_settings
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..money import calculate_change, change_breakdown, q
from ..telegram import (
    send_low_stock_notification,
    send_sale_paid_notification,
    send_stock_notification,
)

router = APIRouter(prefix="/sales", tags=["sales"])
emp_only = require_roles("emp")
management = require_roles("manager", "admin")


def normalize_customer_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", value.strip())
    if not digits:
        return None
    return digits


def ensure_customer_for_sale(db: Session, customer_name: str | None, customer_phone: str | None) -> models.Customer | None:
    phone = normalize_customer_phone(customer_phone)
    if not phone:
        return None
    customer = db.scalar(select(models.Customer).where(models.Customer.phone == phone))
    if customer is None:
        customer = models.Customer(phone=phone, full_name=(customer_name or "").strip() or None)
        db.add(customer)
        db.flush()
    else:
        trimmed_name = (customer_name or "").strip()
        if trimmed_name and customer.full_name != trimmed_name:
            customer.full_name = trimmed_name
    return customer


def get_threshold(db: Session) -> Decimal:
    row = db.get(models.Setting, "approval_threshold")
    return Decimal(row.setting_value) if row else app_settings.APPROVAL_THRESHOLD


def _load_sale(db: Session, sale_id: int, user: models.User) -> models.Sale:
    sale = db.scalar(
        select(models.Sale)
        .options(selectinload(models.Sale.items), selectinload(models.Sale.payment), selectinload(models.Sale.approval))
        .where(models.Sale.id == sale_id)
    )
    if sale is None:
        raise HTTPException(404, "Sale not found")
    # employees may only see their own sales
    if user.role == "emp" and sale.created_by != user.id:
        raise HTTPException(403, "This sale belongs to another employee")
    return sale


PAYWAY_EXPIRY_GRACE = timedelta(minutes=2)


def _payway_lifetime_minutes() -> int:
    return max(3, min(int(app_settings.PAYWAY_QR_LIFETIME_MINUTES), 30 * 24 * 60))


def _new_tran_id(sale_id: int) -> str:
    """PayWay allows at most 20 characters and rejects duplicate IDs."""
    base = f"S{sale_id}"
    suffix = uuid4().hex[:8]
    if len(base) + len(suffix) <= 20:
        return base + suffix
    return f"S{uuid4().hex[:19]}"


def _lock_products(db: Session, sale: models.Sale) -> dict[int, models.Product]:
    ids = sorted({item.product_id for item in sale.items})
    return {
        product.id: product
        for product in db.scalars(
            select(models.Product)
            .where(models.Product.id.in_(ids))
            .order_by(models.Product.id)
            .with_for_update()
        ).all()
    }


def _reserve_stock(db: Session, sale: models.Sale, user: models.User) -> None:
    """Check and deduct stock in one place, used by cash and PayWay checkout."""
    locked = _lock_products(db, sale)
    for item in sale.items:
        product = locked.get(item.product_id)
        if product is None:
            raise HTTPException(409, f"Product {item.product_name} no longer exists")
        if item.quantity > product.stock_qty:
            raise HTTPException(
                409,
                f"Not enough stock for {product.name}: have {product.stock_qty}, need {item.quantity}",
            )
    for item in sale.items:
        product = locked[item.product_id]
        before = product.stock_qty
        product.stock_qty = before - item.quantity
        db.add(models.StockMovement(
            product_id=product.id, movement_type="SALE", quantity=item.quantity,
            qty_before=before, qty_after=product.stock_qty, reference=sale.receipt_no,
            sale_id=sale.id, created_by=user.id,
        ))
        send_stock_notification(
            "OUT", product.name, item.quantity, user.full_name or user.username,
            total_stock=product.stock_qty, reference=sale.receipt_no,
            note=f"Sale {sale.receipt_no}",
        )
        if product.stock_qty <= product.min_stock:
            send_low_stock_notification(
                product.name, product.stock_qty, product.min_stock,
                user.full_name or user.username, reference=sale.receipt_no,
            )


def _release_stock(db: Session, sale: models.Sale, user: models.User, note: str) -> None:
    locked = _lock_products(db, sale)
    for item in sale.items:
        product = locked.get(item.product_id)
        if product is None:
            continue
        before = product.stock_qty
        product.stock_qty = before + item.quantity
        db.add(models.StockMovement(
            product_id=product.id, movement_type="IN", quantity=item.quantity,
            qty_before=before, qty_after=product.stock_qty, reference=sale.receipt_no,
            sale_id=sale.id, created_by=user.id, note=note,
        ))
        send_stock_notification(
            "IN", product.name, item.quantity, user.full_name or user.username,
            total_stock=product.stock_qty, reference=sale.receipt_no, note=note,
        )


def _release_reserved_stock(
    db: Session, sale: models.Sale, payment: models.Payment, user: models.User,
    note: str = "PayWay payment cancelled — stock restored",
) -> None:
    if not payment.stock_reserved:
        return
    _release_stock(db, sale, user, note)
    payment.stock_reserved = False


def _safe_close_payway(tran_id: str | None) -> None:
    """Best-effort invalidation of a pending PayWay QR."""
    if not tran_id or not payway.enabled():
        return
    try:
        payway.close_transaction(tran_id)
    except payway.PaywayError:
        pass


PAYMENT_LABELS = {"CASH": "Cash", "CARD": "Card", "TRANSFER": "Transfer"}


def _notify_sale_paid(sale: models.Sale, user: models.User, payment_label: str) -> None:
    """Send a Telegram alert after the sale is committed as PAID.

    Telegram failures never break a completed sale: the helper swallows
    network errors and simply returns False.
    """
    cashier = sale.cashier
    cashier_name = (
        (cashier.full_name or cashier.username)
        if cashier
        else (user.full_name or user.username)
    )
    send_sale_paid_notification(
        receipt_no=sale.receipt_no,
        total=sale.total,
        payment_label=payment_label,
        cashier_name=cashier_name,
        customer_name=sale.customer_name,
        customer_phone=sale.customer_phone,
        paid_at=sale.paid_at,
    )


def _qr_response(sale: models.Sale, payment: models.Payment) -> dict:
    result: dict = {}
    if payment.raw_response:
        try:
            parsed = json.loads(payment.raw_response)
            if isinstance(parsed, dict):
                result = parsed
        except ValueError:
            result = {}
    expires = payment.expires_at or datetime.now()
    if expires.tzinfo is None:
        # Attach the server's local offset so the browser countdown is correct
        # even when the server and the POS run in different timezones.
        expires = expires.astimezone()
    return {
        "sale_id": sale.id,
        "tran_id": payment.provider_txn_id or "",
        "qr_image": payment.provider_qr or result.get("qrImage"),
        "qr_string": result.get("qrString"),
        "deeplink": result.get("abapay_deeplink"),
        "amount": sale.total,
        "currency": app_settings.PAYWAY_CURRENCY.upper(),
        "expires_at": expires,
        "status": payment.status,
        "sandbox": payway.is_sandbox(),
    }


def _finalize_payway_sale(
    db: Session, sale: models.Sale, payment: models.Payment,
    result: dict, user: models.User,
) -> None:
    if sale.status == "PAID":
        payment.status = "SUCCEEDED"
        db.commit()
        return

    if not payment.stock_reserved:
        try:
            _reserve_stock(db, sale, user)
            payment.stock_reserved = True
        except HTTPException:
            # The customer really paid. Keep the money record correct and
            # leave an audit trail for the stock discrepancy.
            db.add(models.AuditLog(
                actor_id=user.id, action="PAYWAY_STOCK_MISMATCH", entity="sale",
                entity_id=str(sale.id),
                detail=f"PayWay {payment.provider_txn_id} approved but stock was unavailable",
            ))

    payment.status = "SUCCEEDED"
    payment.amount_received = sale.total
    payment.change_given = Decimal("0.00")
    payment.provider_ref = payway.payment_reference(result)
    payment.raw_response = json.dumps(result)[:4000]
    sale.status = "PAID"
    sale.paid_at = datetime.now()
    db.commit()
    _notify_sale_paid(sale, user, "ABA QR")


def _sync_payway_payment(
    db: Session, sale: models.Sale, payment: models.Payment, user: models.User,
    *, force: bool = False,
) -> str:
    """Ask PayWay for the authoritative status and update the local records.

    force=True is used by the webhook: even a locally cancelled/expired
    payment is re-checked, because a customer may have paid the old QR just
    before it was closed.
    """
    if payment.status == "SUCCEEDED" or not payment.provider_txn_id:
        return payment.status
    if not force and payment.status != "PENDING":
        return payment.status
    if not payway.enabled():
        return payment.status

    try:
        result = payway.check_transaction(payment.provider_txn_id)
    except payway.PaywayError as exc:
        if exc.code == "6":  # transaction not found at PayWay
            if payment.status != "PENDING":
                return payment.status
            # Right after QR creation PayWay may briefly not know the ID yet.
            # Do not release stock until the QR lifetime has really passed.
            if payment.expires_at and datetime.now() <= payment.expires_at + PAYWAY_EXPIRY_GRACE:
                return "PENDING"
            _release_reserved_stock(db, sale, payment, user, note="PayWay transaction not found — stock restored")
            payment.status = "EXPIRED"
            payment.raw_response = None
            db.commit()
            return "EXPIRED"
        raise

    state = payway.payment_state(result)
    if state == "APPROVED":
        _finalize_payway_sale(db, sale, payment, result, user)
        return "SUCCEEDED"

    if payment.status != "PENDING":
        # Late callback for a locally cancelled/expired payment: only a
        # verified approval above changes the records.
        return payment.status

    if state in ("DECLINED", "REFUNDED"):
        _release_reserved_stock(db, sale, payment, user, note=f"PayWay payment {state.lower()} — stock restored")
        payment.status = "FAILED"
        payment.raw_response = json.dumps(result)[:4000]
        db.commit()
        return "FAILED"

    if state == "CANCELLED":
        _release_reserved_stock(db, sale, payment, user, note="PayWay payment cancelled — stock restored")
        payment.status = "CANCELLED"
        payment.raw_response = json.dumps(result)[:4000]
        db.commit()
        return "CANCELLED"

    # Still pending. Only expire after the QR lifetime plus a short grace
    # period, so a slightly delayed payment is not released by mistake.
    if payment.expires_at and datetime.now() > payment.expires_at + PAYWAY_EXPIRY_GRACE:
        _safe_close_payway(payment.provider_txn_id)
        _release_reserved_stock(db, sale, payment, user, note="PayWay QR expired — stock restored")
        payment.status = "EXPIRED"
        payment.raw_response = json.dumps(result)[:4000]
        db.commit()
        return "EXPIRED"

    return "PENDING"


@router.post("/change", summary="Preview change for the customer")
def change_preview(data: schemas.ChangeQuery, _: models.User = Depends(emp_only)):
    try:
        change = calculate_change(data.total, data.received)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"total": q(data.total), "received": q(data.received), "change": change,
            "breakdown": change_breakdown(change)}


@router.post("", response_model=schemas.SaleOut, status_code=201)
def create_sale(data: schemas.SaleCreate, db: Session = Depends(get_db), user: models.User = Depends(emp_only)):
    # merge duplicate product lines
    wanted: dict[int, int] = {}
    for it in data.items:
        wanted[it.product_id] = wanted.get(it.product_id, 0) + it.quantity

    products = {
        p.id: p for p in db.scalars(select(models.Product).where(models.Product.id.in_(wanted.keys()))).all()
    }
    items, subtotal = [], Decimal("0")
    for pid, qty in wanted.items():
        p = products.get(pid)
        if p is None or not p.is_active:
            raise HTTPException(400, f"Product {pid} not found or inactive")
        if qty > p.stock_qty:
            raise HTTPException(400, f"Not enough stock for {p.name}: have {p.stock_qty}, need {qty}")
        line = q(p.price * qty)
        subtotal += line
        items.append(models.SaleItem(product_id=p.id, product_name=p.name, unit_price=p.price,
                                     quantity=qty, line_total=line))

    subtotal = q(subtotal)
    discount = q(data.discount)
    if discount > subtotal:
        raise HTTPException(400, "Discount cannot be greater than the subtotal")
    total = q(subtotal - discount)

    customer = ensure_customer_for_sale(db, data.customer_name, data.customer_phone)
    customer_name = (data.customer_name or "").strip() or (customer.full_name if customer else None)
    needs_approval = total > get_threshold(db)
    sale = models.Sale(
        receipt_no=f"TMP-{uuid4().hex[:12]}", customer_id=customer.id if customer else None,
        customer_name=customer_name, subtotal=subtotal, discount=discount, total=total,
        status="PENDING_APPROVAL" if needs_approval else "READY",
        requires_approval=needs_approval, created_by=user.id, items=items,
    )
    db.add(sale)
    db.flush()
    sale.receipt_no = f"R{datetime.now():%Y%m%d}-{sale.id:06d}"
    if needs_approval:
        db.add(models.Approval(sale_id=sale.id, requested_by=user.id))
    db.commit()
    return _load_sale(db, sale.id, user)


@router.post("/{sale_id}/checkout", response_model=schemas.SaleOut)
def checkout(sale_id: int, data: schemas.CheckoutIn, db: Session = Depends(get_db),
             user: models.User = Depends(emp_only)):
    sale = _load_sale(db, sale_id, user)

    if sale.status == "PAID":
        raise HTTPException(400, "Sale is already paid")
    if sale.status == "PENDING_APPROVAL":
        raise HTTPException(403, "This sale is over the limit and still waiting for admin approval")
    if sale.status in ("REJECTED", "CANCELLED"):
        raise HTTPException(400, f"Sale is {sale.status.lower()} and cannot be checked out")
    if sale.requires_approval and sale.status != "APPROVED":
        raise HTTPException(403, "Admin approval is required before checkout")

    # money
    if data.method == "CASH":
        try:
            change = calculate_change(sale.total, data.amount_received)
        except ValueError as e:
            raise HTTPException(400, str(e))
        received = q(data.amount_received)
    else:  # card / transfer are paid exactly
        received, change = sale.total, Decimal("0.00")

    pending = sale.payment
    if pending and pending.status == "PENDING" and pending.provider == "PAYWAY":
        raise HTTPException(
            409,
            "A QR payment is pending. Open QR payment and cancel it before taking another payment.",
        )

    _reserve_stock(db, sale, user)

    # payments.sale_id is unique, so reuse the row after a failed/expired
    # QR attempt instead of inserting a second one.
    payment = sale.payment
    if payment is None:
        payment = models.Payment(sale_id=sale.id, received_by=user.id)
        db.add(payment)
    payment.method = data.method
    payment.amount_due = sale.total
    payment.amount_received = received
    payment.change_given = change
    payment.received_by = user.id
    payment.provider = None
    payment.provider_txn_id = None
    payment.provider_ref = None
    payment.provider_qr = None
    payment.status = "SUCCEEDED"
    payment.stock_reserved = True
    payment.expires_at = None
    payment.raw_response = None

    sale.status = "PAID"
    sale.paid_at = datetime.now()
    db.commit()
    _notify_sale_paid(sale, user, PAYMENT_LABELS.get(data.method, data.method.title()))
    return _load_sale(db, sale.id, user)


@router.post("/{sale_id}/cancel", response_model=schemas.SaleOut)
def cancel(sale_id: int, db: Session = Depends(get_db), user: models.User = Depends(emp_only)):
    sale = _load_sale(db, sale_id, user)
    if sale.status == "PAID":
        raise HTTPException(400, "A paid sale cannot be cancelled")
    if sale.status in ("CANCELLED", "REJECTED"):
        raise HTTPException(400, f"Sale is already {sale.status.lower()}")

    payment = sale.payment
    if payment and payment.status == "PENDING" and payment.provider == "PAYWAY":
        _safe_close_payway(payment.provider_txn_id)
        _release_reserved_stock(db, sale, payment, user, note="Sale cancelled — stock restored")
        payment.status = "CANCELLED"
        payment.raw_response = None

    if sale.approval and sale.approval.status == "PENDING":
        sale.approval.status = "REJECTED"
        sale.approval.decision_note = "Cancelled by employee"
        sale.approval.decided_at = datetime.now()
    sale.status = "CANCELLED"
    db.commit()
    return sale


@router.post("/{sale_id}/payway/qr", response_model=schemas.PaywayQrOut,
             summary="Create an ABA PayWay QR for a sale")
def create_payway_qr(
    sale_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(emp_only),
):
    if not payway.enabled():
        raise HTTPException(
            503,
            "PayWay is not configured. Add PAYWAY_MERCHANT_ID and PAYWAY_API_KEY to the backend .env.",
        )

    sale = _load_sale(db, sale_id, user)
    if sale.status == "PAID":
        raise HTTPException(400, "Sale is already paid")
    if sale.status == "PENDING_APPROVAL":
        raise HTTPException(403, "This sale is over the limit and still waiting for admin approval")
    if sale.status in ("REJECTED", "CANCELLED"):
        raise HTTPException(400, f"Sale is {sale.status.lower()} and cannot be paid")
    if sale.requires_approval and sale.status != "APPROVED":
        raise HTTPException(403, "Admin approval is required before checkout")
    if q(sale.total) < Decimal("0.01"):
        raise HTTPException(400, "This sale total is too small for a QR payment. Please use cash.")

    payment = sale.payment
    now = datetime.now()

    # Reuse a live QR instead of creating a second payable code for one sale.
    if payment and payment.provider == "PAYWAY" and payment.status == "PENDING":
        if payment.expires_at and payment.expires_at > now and payment.provider_qr:
            return _qr_response(sale, payment)
        try:
            state = _sync_payway_payment(db, sale, payment, user)
        except payway.PaywayError as exc:
            raise HTTPException(502, exc.message)
        if state == "SUCCEEDED":
            raise HTTPException(409, "This sale has already been paid")
        if payment.status == "PENDING":
            # PayWay still reports pending; keep showing the same QR.
            return _qr_response(sale, payment)

    if payment and payment.provider == "PAYWAY":
        # A QR cancelled or expired locally may still have been paid just
        # before PayWay closed it. Re-check before issuing a replacement code
        # so the customer is never charged twice.
        if payment.status in ("CANCELLED", "FAILED", "EXPIRED") and payment.provider_txn_id:
            try:
                state = _sync_payway_payment(db, sale, payment, user, force=True)
            except payway.PaywayError as exc:
                raise HTTPException(502, exc.message)
            if state == "SUCCEEDED" or sale.status == "PAID":
                raise HTTPException(409, "This sale has already been paid")
        if payment.stock_reserved:
            # Make sure the previous QR can no longer be paid before its stock
            # reservation is released and a replacement code is generated.
            _safe_close_payway(payment.provider_txn_id)
            _release_reserved_stock(db, sale, payment, user, note="PayWay QR replaced — stock restored")
            db.commit()

    lifetime = _payway_lifetime_minutes()
    tran_id = _new_tran_id(sale.id)
    try:
        result = payway.generate_qr(
            tran_id=tran_id,
            amount=sale.total,
            items=[
                {"name": item.product_name, "quantity": item.quantity, "price": item.unit_price}
                for item in sale.items
            ],
            lifetime_minutes=lifetime,
        )
    except payway.PaywayError as exc:
        raise HTTPException(502, exc.message)

    try:
        _reserve_stock(db, sale, user)
    except HTTPException:
        _safe_close_payway(tran_id)
        raise

    if payment is None:
        payment = models.Payment(sale_id=sale.id, received_by=user.id)
        db.add(payment)
    payment.method = "TRANSFER"
    payment.amount_due = sale.total
    payment.amount_received = Decimal("0.00")
    payment.change_given = Decimal("0.00")
    payment.received_by = user.id
    payment.provider = "PAYWAY"
    payment.provider_txn_id = tran_id
    payment.provider_ref = None
    payment.provider_qr = result.get("qrImage")
    payment.status = "PENDING"
    payment.stock_reserved = True
    payment.expires_at = now + timedelta(minutes=lifetime)
    payment.raw_response = json.dumps(result)[:4000]
    db.commit()
    db.refresh(payment)
    return _qr_response(sale, payment)


@router.get("/{sale_id}/payway/status", response_model=schemas.PaywayStatusOut,
            summary="Poll the ABA PayWay status for a sale")
def payway_status(
    sale_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(emp_only),
):
    sale = _load_sale(db, sale_id, user)
    payment = sale.payment

    if sale.status == "PAID":
        return {
            "sale_id": sale.id,
            "status": "SUCCEEDED",
            "sale_status": sale.status,
            "sale": sale,
        }
    if payment is None or payment.provider != "PAYWAY":
        raise HTTPException(404, "No PayWay payment found for this sale")

    try:
        state = _sync_payway_payment(db, sale, payment, user)
    except payway.PaywayError as exc:
        # Network / API hiccup: keep the sale pending and let the UI retry.
        return {
            "sale_id": sale.id,
            "status": payment.status,
            "sale_status": sale.status,
            "message": exc.message,
        }

    sale = _load_sale(db, sale.id, user)
    message = None
    if state not in ("PENDING", "SUCCEEDED"):
        message = f"Payment {state.lower()}."
    return {
        "sale_id": sale.id,
        "status": state,
        "sale_status": sale.status,
        "sale": sale if sale.status == "PAID" else None,
        "message": message,
    }


@router.post("/{sale_id}/payway/cancel", response_model=schemas.PaywayStatusOut,
             summary="Cancel a pending ABA PayWay QR")
def cancel_payway(
    sale_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(emp_only),
):
    sale = _load_sale(db, sale_id, user)
    if sale.status == "PAID":
        raise HTTPException(400, "Sale is already paid")

    payment = sale.payment
    if payment is None or payment.provider != "PAYWAY":
        raise HTTPException(404, "No PayWay payment found for this sale")

    if payment.status == "PENDING":
        try:
            state = _sync_payway_payment(db, sale, payment, user)
        except payway.PaywayError:
            state = "PENDING"
        if state == "SUCCEEDED" or sale.status == "PAID":
            sale = _load_sale(db, sale.id, user)
            return {
                "sale_id": sale.id,
                "status": "SUCCEEDED",
                "sale_status": sale.status,
                "sale": sale,
            }
        if payment.status == "PENDING":
            _safe_close_payway(payment.provider_txn_id)
            _release_reserved_stock(db, sale, payment, user, note="PayWay QR cancelled — stock restored")
            payment.status = "CANCELLED"
            payment.raw_response = None
            db.commit()

    return {
        "sale_id": sale.id,
        "status": payment.status,
        "sale_status": sale.status,
        "message": "QR payment cancelled.",
    }


@router.get("", response_model=list[schemas.SaleOut])
def list_sales(
    status: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stmt = (select(models.Sale)
            .options(selectinload(models.Sale.items), selectinload(models.Sale.payment), selectinload(models.Sale.approval))
            .order_by(models.Sale.id.desc()).limit(limit))
    if user.role == "emp":
        stmt = stmt.where(models.Sale.created_by == user.id)
    if status:
        stmt = stmt.where(models.Sale.status == status)
    if start:
        stmt = stmt.where(models.Sale.created_at >= datetime.combine(start, datetime.min.time()))
    if end:
        stmt = stmt.where(models.Sale.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()))
    return db.scalars(stmt).all()


@router.get("/employee-sales", response_model=schemas.EmployeeSalesOut,
            summary="Daily employee sales for managers and admins")
def employee_sales(
    day: date | None = None,
    employee_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(management),
):
    target_day = day or date.today()
    start = datetime.combine(target_day, datetime.min.time())
    end = start + timedelta(days=1)
    recorded_at = func.coalesce(models.Sale.paid_at, models.Sale.created_at)

    stmt = (
        select(models.Sale)
        .options(selectinload(models.Sale.cashier), selectinload(models.Sale.customer))
        .where(recorded_at >= start, recorded_at < end)
        .order_by(recorded_at.desc(), models.Sale.id.desc())
    )
    if employee_id:
        stmt = stmt.where(models.Sale.created_by == employee_id)
    if status:
        stmt = stmt.where(models.Sale.status == status)

    sales = db.scalars(stmt).all()
    paid = [sale for sale in sales if sale.status == "PAID"]
    employees = db.scalars(
        select(models.User)
        .where(models.User.role == "emp")
        .order_by(models.User.full_name, models.User.username)
    ).all()

    return {
        "day": target_day,
        "count": len(sales),
        "paid_count": len(paid),
        "total": sum((sale.total for sale in paid), Decimal("0.00")),
        "sales": [
            {
                "id": sale.id,
                "receipt_no": sale.receipt_no,
                "customer_name": sale.customer_name or (
                    sale.customer.full_name if sale.customer else None
                ),
                "customer_phone": sale.customer.phone if sale.customer else None,
                "total": sale.total,
                "status": sale.status,
                "created_at": sale.created_at,
                "paid_at": sale.paid_at,
                "employee_id": sale.created_by,
                "employee_name": sale.cashier.full_name if sale.cashier else "Unknown",
                "employee_username": sale.cashier.username if sale.cashier else "",
            }
            for sale in sales
        ],
        "employees": [
            {"id": employee.id, "full_name": employee.full_name, "username": employee.username}
            for employee in employees
        ],
    }


@router.get("/employee-sales/employees", response_model=list[schemas.EmployeeOptionOut],
            summary="Employees available in the employee sales filter")
def employee_sales_employees(
    db: Session = Depends(get_db),
    _: models.User = Depends(management),
):
    employees = db.scalars(
        select(models.User)
        .where(models.User.role == "emp")
        .order_by(models.User.full_name, models.User.username)
    ).all()
    return [
        {"id": employee.id, "full_name": employee.full_name, "username": employee.username}
        for employee in employees
    ]


@router.get("/{sale_id}", response_model=schemas.SaleOut)
def get_sale(sale_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _load_sale(db, sale_id, user)


@router.get("/{sale_id}/receipt", summary="Receipt data for printing")
def receipt(sale_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sale = _load_sale(db, sale_id, user)
    if sale.status != "PAID" or sale.payment is None:
        raise HTTPException(400, "Receipt is available only for paid sales")
    return {
        "receipt_no": sale.receipt_no,
        "date": sale.paid_at,
        "cashier": sale.cashier.full_name,
        "customer_name": sale.customer_name,
        "items": [{"name": i.product_name, "qty": i.quantity, "unit_price": i.unit_price,
                   "line_total": i.line_total} for i in sale.items],
        "subtotal": sale.subtotal, "discount": sale.discount, "total": sale.total,
        "payment_method": sale.payment.method,
        "payment_status": sale.payment.status,
        "payment_provider": sale.payment.provider,
        "payment_reference": sale.payment.provider_ref,
        "amount_received": sale.payment.amount_received,
        "change": sale.payment.change_given,
        "change_breakdown": change_breakdown(sale.payment.change_given),
    }
