from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
from app.main import app
from app.models import AuditLog, Base, LoginLog, Product, User
from app.retention import purge_expired_logs
from app.security import create_access_token

MANAGER_USERNAME = "logs_manager"
CASHIER_USERNAME = "logs_cashier"


def _local_offset() -> timedelta:
    return datetime.now().astimezone().utcoffset() or timedelta(0)


def _utc_at_local_noon(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=12) - _local_offset()


@pytest.fixture
def logs_env(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    Base.metadata.create_all(bind=engine)

    with sessions() as db:
        manager = User(
            username=MANAGER_USERNAME,
            password_hash="hash",
            full_name="Logs Manager",
            role="manager",
            is_active=True,
        )
        cashier = User(
            username=CASHIER_USERNAME,
            password_hash="hash",
            full_name="Logs Cashier",
            role="emp",
            is_active=True,
        )
        product = Product(
            sku="LOG-TEST-1",
            name="Log test product",
            unit="pcs",
            price=Decimal("5.00"),
            cost=Decimal("2.00"),
            stock_qty=10,
            min_stock=0,
        )
        db.add_all([manager, cashier, product])
        db.flush()
        ids = {
            "manager": manager.id,
            "cashier": cashier.id,
            "product": product.id,
        }
        manager_token = create_access_token(manager.id, manager.role)
        cashier_token = create_access_token(cashier.id, cashier.role)
        db.commit()

    with TestClient(app) as client:
        yield {
            "client": client,
            "sessions": sessions,
            "ids": ids,
            "manager_headers": {"Authorization": f"Bearer {manager_token}"},
            "cashier_headers": {"Authorization": f"Bearer {cashier_token}"},
        }

    engine.dispose()


def test_mutating_request_is_audited_with_username_and_ip(logs_env):
    headers = {**logs_env["manager_headers"], "CF-Connecting-IP": "203.0.113.77"}
    response = logs_env["client"].post(
        "/api/stock/in",
        json={"product_id": logs_env["ids"]["product"], "quantity": 3},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    with logs_env["sessions"]() as db:
        row = db.scalar(select(AuditLog).where(AuditLog.action == "POST /stock/in"))
        assert row is not None
        assert row.actor_id == logs_env["ids"]["manager"]
        assert row.username == MANAGER_USERNAME
        assert row.ip_address == "203.0.113.77"
        assert row.entity == "stock"


def test_explicit_audit_is_not_duplicated_and_has_username_and_ip(logs_env):
    headers = {**logs_env["manager_headers"], "CF-Connecting-IP": "198.51.100.20"}
    response = logs_env["client"].post(
        "/api/products",
        json={"sku": "LOG-NEW-1", "name": "New log product", "price": "4.50"},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    with logs_env["sessions"]() as db:
        rows = db.scalars(
            select(AuditLog).where(
                AuditLog.action.in_(("PRODUCT_CREATED", "POST /products"))
            )
        ).all()
        assert [row.action for row in rows] == ["PRODUCT_CREATED"]
        assert rows[0].username == MANAGER_USERNAME
        assert rows[0].ip_address == "198.51.100.20"


def test_audit_and_login_date_filters(logs_env):
    today = date.today()
    yesterday = today - timedelta(days=1)
    with logs_env["sessions"]() as db:
        db.add_all([
            AuditLog(
                actor_id=logs_env["ids"]["manager"], username=MANAGER_USERNAME,
                action="TEST_TODAY", entity="test", created_at=_utc_at_local_noon(today),
            ),
            AuditLog(
                actor_id=logs_env["ids"]["manager"], username=MANAGER_USERNAME,
                action="TEST_YESTERDAY", entity="test", created_at=_utc_at_local_noon(yesterday),
            ),
            LoginLog(
                user_id=logs_env["ids"]["manager"], username="filter_today",
                event="LOGIN", created_at=_utc_at_local_noon(today),
            ),
            LoginLog(
                user_id=logs_env["ids"]["manager"], username="filter_yesterday",
                event="LOGIN", created_at=_utc_at_local_noon(yesterday),
            ),
        ])
        db.commit()

    audit_response = logs_env["client"].get(
        "/api/logs/audit",
        params={"start": today.isoformat(), "end": today.isoformat()},
        headers=logs_env["manager_headers"],
    )
    assert audit_response.status_code == 200, audit_response.text
    actions = {row["action"] for row in audit_response.json()}
    assert "TEST_TODAY" in actions
    assert "TEST_YESTERDAY" not in actions

    login_response = logs_env["client"].get(
        "/api/logs/logins",
        params={"start": today.isoformat(), "end": today.isoformat()},
        headers=logs_env["manager_headers"],
    )
    assert login_response.status_code == 200, login_response.text
    usernames = {row["username"] for row in login_response.json()}
    assert "filter_today" in usernames
    assert "filter_yesterday" not in usernames


def test_manager_deletes_logs_by_date_and_clear_all_is_audited(logs_env):
    today = date.today()
    two_days_ago = today - timedelta(days=2)
    with logs_env["sessions"]() as db:
        db.add_all([
            LoginLog(user_id=logs_env["ids"]["manager"], username="delete_today",
                     event="LOGIN", created_at=_utc_at_local_noon(today)),
            LoginLog(user_id=logs_env["ids"]["manager"], username="delete_old",
                     event="LOGIN", created_at=_utc_at_local_noon(two_days_ago)),
        ])
        db.commit()

    headers = {**logs_env["manager_headers"], "CF-Connecting-IP": "192.0.2.55"}
    deleted = logs_env["client"].delete(
        "/api/logs/logins",
        params={"start": today.isoformat(), "end": today.isoformat()},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1

    with logs_env["sessions"]() as db:
        remaining = db.scalars(select(LoginLog)).all()
        assert [row.username for row in remaining] == ["delete_old"]
        audit_row = db.scalar(
            select(AuditLog).where(AuditLog.action == "LOGIN_LOGS_DELETED")
        )
        assert audit_row is not None
        assert audit_row.username == MANAGER_USERNAME
        assert audit_row.ip_address == "192.0.2.55"
        assert "range=" in (audit_row.detail or "")

    cleared = logs_env["client"].delete(
        "/api/logs/logins/all", headers=headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted"] == 1

    with logs_env["sessions"]() as db:
        assert db.scalar(select(func.count()).select_from(LoginLog)) == 0
        audit_row = db.scalar(
            select(AuditLog).where(AuditLog.action == "LOGIN_LOGS_CLEARED")
        )
        assert audit_row is not None
        assert audit_row.username == MANAGER_USERNAME
        assert "all sign-in records" in (audit_row.detail or "")

    audit_cleared = logs_env["client"].delete(
        "/api/logs/audit/all", headers=headers
    )
    assert audit_cleared.status_code == 200, audit_cleared.text

    with logs_env["sessions"]() as db:
        rows = db.scalars(select(AuditLog)).all()
        assert len(rows) == 1
        assert rows[0].action == "AUDIT_LOGS_CLEARED"
        assert rows[0].username == MANAGER_USERNAME
        assert rows[0].ip_address == "192.0.2.55"


def test_only_manager_can_delete_logs(logs_env):
    response = logs_env["client"].delete(
        "/api/logs/logins/all", headers=logs_env["cashier_headers"]
    )
    assert response.status_code == 403, response.text


def test_retention_removes_records_older_than_seven_days(logs_env):
    old = datetime.utcnow() - timedelta(days=8)
    recent = datetime.utcnow() - timedelta(hours=1)
    with logs_env["sessions"]() as db:
        db.add_all([
            LoginLog(user_id=logs_env["ids"]["manager"], username="old_login",
                     event="LOGIN", created_at=old),
            LoginLog(user_id=logs_env["ids"]["manager"], username="recent_login",
                     event="LOGIN", created_at=recent),
            AuditLog(actor_id=logs_env["ids"]["manager"], username=MANAGER_USERNAME,
                     action="OLD_AUDIT", entity="test", created_at=old),
            AuditLog(actor_id=logs_env["ids"]["manager"], username=MANAGER_USERNAME,
                     action="RECENT_AUDIT", entity="test", created_at=recent),
        ])
        db.commit()

    result = purge_expired_logs()
    assert result == {"logins": 1, "audit": 1}

    with logs_env["sessions"]() as db:
        assert [row.username for row in db.scalars(select(LoginLog)).all()] == ["recent_login"]
        assert [row.action for row in db.scalars(select(AuditLog)).all()] == ["RECENT_AUDIT"]
