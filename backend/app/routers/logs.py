"""Login/logout tracking and audit trail - MANAGER only.

Both logs keep only LOG_RETENTION_DAYS (default 7) days. Managers can also
filter by date and delete records for a selected date range or clear a log.
Every deletion is itself recorded in the audit trail with the manager's
username, IP address, count, and deleted date range.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..deps import audit, client_info, require_roles
from ..retention import purge_expired_logs

router = APIRouter(prefix="/logs", tags=["logs"])
manager_only = require_roles("manager")


class LoginLogOut(BaseModel):
    id: int
    user_id: int | None
    username: str
    event: str
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None
    username: str | None
    ip_address: str | None
    action: str
    entity: str
    entity_id: str | None
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


def _local_offset() -> timedelta:
    """Current server UTC offset, used to turn local calendar dates into the
    UTC timestamps stored by the database."""
    return datetime.now().astimezone().utcoffset() or timedelta(0)


def _day_start(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time()) - _local_offset()


def _day_end(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), datetime.min.time()) - _local_offset()


def _apply_dates(stmt, model, start: date | None, end: date | None):
    if start:
        stmt = stmt.where(model.created_at >= _day_start(start))
    if end:
        stmt = stmt.where(model.created_at < _day_end(end))
    return stmt


def _validate_delete_range(start: date | None, end: date | None) -> None:
    if start is None and end is None:
        raise HTTPException(400, "Choose a start date, an end date, or both.")
    if start and end and start > end:
        raise HTTPException(400, "The start date must be on or before the end date.")


def _range_label(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{start.isoformat()}..{end.isoformat()}"
    if start:
        return f"from {start.isoformat()}"
    return f"through {end.isoformat()}"


@router.get("/logins", response_model=list[LoginLogOut])
def login_logs(
    user_id: int | None = None,
    event: str | None = Query(None, pattern="^(LOGIN|LOGOUT|LOGIN_FAILED)$"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _=Depends(manager_only),
):
    purge_expired_logs(db)
    stmt = select(models.LoginLog).order_by(models.LoginLog.id.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(models.LoginLog.user_id == user_id)
    if event:
        stmt = stmt.where(models.LoginLog.event == event)
    stmt = _apply_dates(stmt, models.LoginLog, start, end)
    return db.scalars(stmt).all()


@router.get("/audit", response_model=list[AuditLogOut])
def audit_logs(
    start: date | None = None,
    end: date | None = None,
    username: str | None = Query(None, max_length=50),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _=Depends(manager_only),
):
    purge_expired_logs(db)
    stmt = select(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(limit)
    stmt = _apply_dates(stmt, models.AuditLog, start, end)
    if username:
        stmt = stmt.where(models.AuditLog.username.ilike(f"%{username.strip()}%"))
    return db.scalars(stmt).all()


@router.get("/retention")
def retention_settings(_=Depends(manager_only)):
    return {"days": settings.LOG_RETENTION_DAYS}


@router.delete("/logins/all")
def clear_login_logs(
    request: Request,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    """Delete every sign-in record. The deletion itself is audited."""
    count = db.execute(delete(models.LoginLog)).rowcount or 0
    ip, _ = client_info(request)
    audit(
        db, manager.id, "LOGIN_LOGS_CLEARED", "login_log", None,
        f"deleted={count} all sign-in records",
        request=request, username=manager.username, ip_address=ip,
    )
    db.commit()
    return {"deleted": count}


@router.delete("/logins")
def delete_login_logs(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    """Delete sign-in records in a date range (inclusive) and audit it."""
    _validate_delete_range(start, end)
    stmt = _apply_dates(delete(models.LoginLog), models.LoginLog, start, end)
    count = db.execute(stmt).rowcount or 0
    ip, _ = client_info(request)
    audit(
        db, manager.id, "LOGIN_LOGS_DELETED", "login_log", None,
        f"deleted={count} range={_range_label(start, end)}",
        request=request, username=manager.username, ip_address=ip,
    )
    db.commit()
    return {"deleted": count}


@router.delete("/audit/all")
def clear_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    """Delete every audit record, then write one audit record for the action."""
    count = db.execute(delete(models.AuditLog)).rowcount or 0
    ip, _ = client_info(request)
    audit(
        db, manager.id, "AUDIT_LOGS_CLEARED", "audit_log", None,
        f"deleted={count} all audit records",
        request=request, username=manager.username, ip_address=ip,
    )
    db.commit()
    return {"deleted": count}


@router.delete("/audit")
def delete_audit_logs(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    """Delete audit records in a date range (inclusive) and record the action."""
    _validate_delete_range(start, end)
    stmt = _apply_dates(delete(models.AuditLog), models.AuditLog, start, end)
    count = db.execute(stmt).rowcount or 0
    ip, _ = client_info(request)
    audit(
        db, manager.id, "AUDIT_LOGS_DELETED", "audit_log", None,
        f"deleted={count} range={_range_label(start, end)}",
        request=request, username=manager.username, ip_address=ip,
    )
    db.commit()
    return {"deleted": count}
