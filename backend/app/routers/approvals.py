"""Approvals for sales above the threshold.
- admin   : approve / reject
- manager : tracks (read-only) every approval decision
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import audit, require_roles
from ..telegram import send_approval_notification

router = APIRouter(prefix="/approvals", tags=["approvals"])
admin_only = require_roles("admin")
viewers = require_roles("admin", "manager")


@router.get("", response_model=list[schemas.ApprovalRow])
def list_approvals(status: str | None = None, db: Session = Depends(get_db), _=Depends(viewers)):
    stmt = (select(models.Approval, models.Sale).join(models.Sale, models.Sale.id == models.Approval.sale_id)
            .order_by(models.Approval.id.desc()).limit(300))
    if status:
        stmt = stmt.where(models.Approval.status == status)
    rows = []
    for ap, sale in db.execute(stmt).all():
        rows.append(schemas.ApprovalRow(
            approval_id=ap.id, sale_id=sale.id, receipt_no=sale.receipt_no, total=sale.total,
            requested_by=ap.requester.full_name, requested_at=ap.requested_at, status=ap.status,
            decided_by=ap.decider.full_name if ap.decider else None,
            decided_at=ap.decided_at, decision_note=ap.decision_note,
        ))
    return rows


def _decide(db: Session, approval_id: int, admin: models.User, approve: bool, note: str | None,
            request: Request):
    ap = db.scalar(select(models.Approval).where(models.Approval.id == approval_id).with_for_update())
    if ap is None:
        raise HTTPException(404, "Approval not found")
    if ap.status != "PENDING":
        raise HTTPException(409, f"Already {ap.status.lower()}")
    sale = db.get(models.Sale, ap.sale_id)
    if sale.status != "PENDING_APPROVAL":
        raise HTTPException(409, f"Sale is {sale.status.lower()} - nothing to approve")

    ap.status = "APPROVED" if approve else "REJECTED"
    ap.decided_by, ap.decided_at, ap.decision_note = admin.id, datetime.now(), note
    sale.status = "APPROVED" if approve else "REJECTED"
    audit(db, admin.id, "SALE_APPROVED" if approve else "SALE_REJECTED", "sale", sale.id,
          f"{sale.receipt_no} total={sale.total}",
          request=request, username=admin.username)
    db.commit()
    if sale.total >= settings.APPROVAL_THRESHOLD:
        send_approval_notification(
            "APPROVED" if approve else "REJECTED",
            sale.receipt_no,
            sale.total,
            admin.full_name or admin.username,
            note,
        )
    return {"approval_id": ap.id, "sale_id": sale.id, "status": ap.status}


@router.post("/{approval_id}/approve")
def approve(approval_id: int, body: schemas.ApprovalDecision, request: Request,
            db: Session = Depends(get_db), admin: models.User = Depends(admin_only)):
    return _decide(db, approval_id, admin, True, body.note, request)


@router.post("/{approval_id}/reject")
def reject(approval_id: int, body: schemas.ApprovalDecision, request: Request,
           db: Session = Depends(get_db), admin: models.User = Depends(admin_only)):
    return _decide(db, approval_id, admin, False, body.note, request)
