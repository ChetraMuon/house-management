"""Automatic retention for sign-in and audit records.

Both tables keep only the last LOG_RETENTION_DAYS (default 7) days. Cleanup runs
at startup, before log queries, and once an hour in the background.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import database, models
from .config import settings

logger = logging.getLogger("house.retention")
RETENTION_INTERVAL_SECONDS = 60 * 60


def purge_expired_logs(db: Session | None = None) -> dict[str, int]:
    """Delete login/audit rows older than the configured retention period."""
    owns_session = db is None
    session = db or database.SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=max(1, settings.LOG_RETENTION_DAYS))
        logins = session.execute(
            delete(models.LoginLog).where(models.LoginLog.created_at < cutoff)
        ).rowcount or 0
        audits = session.execute(
            delete(models.AuditLog).where(models.AuditLog.created_at < cutoff)
        ).rowcount or 0
        session.commit()
        return {"logins": logins, "audit": audits}
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


async def retention_loop() -> None:
    while True:
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)
        try:
            purge_expired_logs()
        except Exception:  # never let cleanup stop the background task
            logger.exception("Automatic log retention failed")
