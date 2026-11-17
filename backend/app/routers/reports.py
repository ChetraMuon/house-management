"""Reports.
- emp      : daily + range report of their OWN sales
- admin    : view all reports
- manager  : view / generate all reports (+ CSV export)
"""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/reports", tags=["reports"])
staff = require_roles("manager", "admin")


def _bounds(start: date, end: date):
    return datetime.combine(start, datetime.min.time()), datetime.combine(end + timedelta(days=1), datetime.min.time())


def _sales_summary(db: Session, start: date, end: date, user_id: int | None):
    s, e = _bounds(start, end)
    base = [models.Sale.status == "PAID", models.Sale.paid_at >= s, models.Sale.paid_at < e]
    if user_id:
        base.append(models.Sale.created_by == user_id)

    count, revenue, discount = db.execute(
        select(func.count(models.Sale.id), func.coalesce(func.sum(models.Sale.total), 0),
               func.coalesce(func.sum(models.Sale.discount), 0)).where(*base)
    ).one()

    by_method = db.execute(
        select(models.Payment.method, func.count(models.Payment.id),
               func.coalesce(func.sum(models.Payment.amount_due), 0))
        .join(models.Sale, models.Sale.id == models.Payment.sale_id).where(*base)
        .group_by(models.Payment.method)
    ).all()

    cash = db.execute(
        select(func.coalesce(func.sum(models.Payment.amount_received), 0),
               func.coalesce(func.sum(models.Payment.change_given), 0))
        .join(models.Sale, models.Sale.id == models.Payment.sale_id)
        .where(*base, models.Payment.method == "CASH")
    ).one()

    products = db.execute(
        select(models.SaleItem.product_name, func.sum(models.SaleItem.quantity),
               func.sum(models.SaleItem.line_total))
        .join(models.Sale, models.Sale.id == models.SaleItem.sale_id).where(*base)
        .group_by(models.SaleItem.product_name).order_by(func.sum(models.SaleItem.line_total).desc())
    ).all()

    per_day = db.execute(
        select(func.date(models.Sale.paid_at), func.count(models.Sale.id), func.sum(models.Sale.total))
        .where(*base).group_by(func.date(models.Sale.paid_at)).order_by(func.date(models.Sale.paid_at))
    ).all()

    return {
        "start": start, "end": end,
        "sales_count": count, "revenue": revenue, "discount": discount,
        "cash_received": cash[0], "cash_change_given": cash[1], "cash_net": Decimal(cash[0]) - Decimal(cash[1]),
        "by_method": [{"method": m, "count": c, "amount": a} for m, c, a in by_method],
        "products": [{"name": n, "qty": int(qty), "amount": a} for n, qty, a in products],
        "per_day": [{"date": str(d), "count": c, "amount": a} for d, c, a in per_day],
    }


def _scope(user: models.User, user_id: int | None) -> int | None:
    """emp is always limited to own data; manager/admin may filter by user."""
    return user.id if user.role == "emp" else user_id


@router.get("/daily")
def daily(day: date | None = None, user_id: int | None = None,
          db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    day = day or date.today()
    return _sales_summary(db, day, day, _scope(user, user_id))


@router.get("/sales")
def sales_range(start: date, end: date, user_id: int | None = None,
                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _sales_summary(db, start, end, _scope(user, user_id))


@router.get("/sales.csv")
def sales_csv(start: date, end: date, user_id: int | None = None,
              db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s, e = _bounds(start, end)
    stmt = (select(models.Sale).where(models.Sale.status == "PAID", models.Sale.paid_at >= s, models.Sale.paid_at < e)
            .order_by(models.Sale.paid_at))
    scoped = _scope(user, user_id)
    if scoped:
        stmt = stmt.where(models.Sale.created_by == scoped)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["receipt_no", "paid_at", "cashier", "customer", "subtotal", "discount", "total", "method", "received", "change"])
    for sale in db.scalars(stmt).all():
        p = sale.payment
        w.writerow([sale.receipt_no, sale.paid_at, sale.cashier.full_name, sale.customer_name or "",
                    sale.subtotal, sale.discount, sale.total,
                    p.method if p else "", p.amount_received if p else "", p.change_given if p else ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="sales_{start}_{end}.csv"'})


@router.get("/stock")
def stock_report(db: Session = Depends(get_db), _=Depends(staff)):
    products = db.scalars(select(models.Product).where(models.Product.is_active.is_(True))
                          .order_by(models.Product.name)).all()
    rows = [{
        "id": p.id, "sku": p.sku, "name": p.name, "stock_qty": p.stock_qty, "min_stock": p.min_stock,
        "low": p.stock_qty <= p.min_stock, "price": p.price, "cost": p.cost,
        "stock_value": p.cost * p.stock_qty, "retail_value": p.price * p.stock_qty,
    } for p in products]
    return {
        "total_items": len(rows),
        "total_units": sum(r["stock_qty"] for r in rows),
        "total_cost_value": sum(r["stock_value"] for r in rows),
        "total_retail_value": sum(r["retail_value"] for r in rows),
        "low_stock": [r for r in rows if r["low"]],
        "products": rows,
    }
