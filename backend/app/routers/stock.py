"""Stock control.
- manager: stock in / out / adjust / view movements
- admin:   stock in / out / view movements
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles
from ..telegram import send_low_stock_notification, send_stock_notification

router = APIRouter(prefix="/stock", tags=["stock"])
stock_staff = require_roles("manager", "admin")
manager_only = require_roles("manager")


def _locked_product(db: Session, product_id: int) -> models.Product:
    product = db.scalar(
        select(models.Product).where(models.Product.id == product_id).with_for_update()
    )
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


def _record(db, product, mtype, qty, before, user, reference=None, note=None, sale_id=None):
    db.add(models.StockMovement(
        product_id=product.id, movement_type=mtype, quantity=qty,
        qty_before=before, qty_after=product.stock_qty,
        reference=reference, note=note, sale_id=sale_id, created_by=user.id,
    ))


def _maybe_notify_low_stock(product, actor_name: str | None = None, reference: str | None = None):
    if product.stock_qty <= product.min_stock:
        send_low_stock_notification(product.name, product.stock_qty, product.min_stock, actor_name, reference)


@router.post("/in", response_model=schemas.ProductOut)
def stock_in(data: schemas.StockChange, db: Session = Depends(get_db), user=Depends(stock_staff)):
    product = _locked_product(db, data.product_id)
    before = product.stock_qty
    product.stock_qty = before + data.quantity
    _record(db, product, "IN", data.quantity, before, user, data.reference, data.note)
    db.commit()
    send_stock_notification(
        "IN",
        product.name,
        data.quantity,
        user.full_name or user.username,
        total_stock=product.stock_qty,
        reference=data.reference,
        note=data.note,
    )
    _maybe_notify_low_stock(product, user.full_name or user.username, data.reference)
    return product


@router.post("/out", response_model=schemas.ProductOut)
def stock_out(data: schemas.StockChange, db: Session = Depends(get_db), user=Depends(stock_staff)):
    product = _locked_product(db, data.product_id)
    before = product.stock_qty
    if data.quantity > before:
        raise HTTPException(400, f"Not enough stock for {product.name}: have {before}, need {data.quantity}")
    product.stock_qty = before - data.quantity
    _record(db, product, "OUT", data.quantity, before, user, data.reference, data.note)
    db.commit()
    send_stock_notification(
        "OUT",
        product.name,
        data.quantity,
        user.full_name or user.username,
        total_stock=product.stock_qty,
        reference=data.reference,
        note=data.note,
    )
    _maybe_notify_low_stock(product, user.full_name or user.username, data.reference)
    return product


@router.post("/adjust", response_model=schemas.ProductOut)
def stock_adjust(data: schemas.StockAdjust, db: Session = Depends(get_db), user=Depends(manager_only)):
    product = _locked_product(db, data.product_id)
    before = product.stock_qty
    product.stock_qty = data.new_quantity
    _record(db, product, "ADJUST", abs(data.new_quantity - before), before, user, None, data.note)
    db.commit()
    _maybe_notify_low_stock(product, user.full_name or user.username)
    return product


@router.get("/movements", response_model=list[schemas.StockMovementOut])
def movements(
    product_id: int | None = None,
    movement_type: str | None = Query(None, pattern="^(IN|OUT|ADJUST|SALE)$"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _=Depends(stock_staff),
):
    stmt = select(models.StockMovement).order_by(models.StockMovement.id.desc()).limit(limit)
    if product_id:
        stmt = stmt.where(models.StockMovement.product_id == product_id)
    if movement_type:
        stmt = stmt.where(models.StockMovement.movement_type == movement_type)
    if start:
        stmt = stmt.where(models.StockMovement.created_at >= datetime.combine(start, datetime.min.time()))
    if end:
        stmt = stmt.where(models.StockMovement.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()))
    return db.scalars(stmt).all()
