import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles


def normalize_customer_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", value.strip())
    if not digits:
        return None
    return digits

router = APIRouter(prefix="/customers", tags=["customers"])
management = require_roles("manager", "admin")


@router.get("", response_model=list[schemas.CustomerOut])
def list_customers(
    phone: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(management),
):
    stmt = select(models.Customer).order_by(models.Customer.created_at.desc())
    normalized_phone = normalize_customer_phone(phone)
    if normalized_phone:
        stmt = stmt.where(models.Customer.phone == normalized_phone)
    return db.scalars(stmt).all()


@router.get("/{customer_id}/history", response_model=schemas.CustomerHistoryOut)
def customer_history(customer_id: int, db: Session = Depends(get_db), _=Depends(management)):
    customer = db.get(models.Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    purchases = db.scalars(
        select(models.Sale)
        .options(selectinload(models.Sale.items))
        .where(models.Sale.customer_id == customer_id)
        .order_by(models.Sale.created_at.desc())
    ).all()
    return {
        "customer": customer,
        "purchases": [
            {
                "id": sale.id,
                "receipt_no": sale.receipt_no,
                "subtotal": sale.subtotal,
                "discount": sale.discount,
                "total": sale.total,
                "created_at": sale.created_at,
                "status": sale.status,
                "items": [
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "unit_price": item.unit_price,
                        "quantity": item.quantity,
                        "line_total": item.line_total,
                    }
                    for item in sale.items
                ],
            }
            for sale in purchases
        ],
        "total_spent": sum((sale.total for sale in purchases), 0),
    }
