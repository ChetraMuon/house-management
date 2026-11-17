from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
from app import models
from app.main import app
from app.models import Base, Customer, Sale, User
from app.routers.sales import ensure_customer_for_sale
from app.security import create_access_token, hash_password


database.engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=database.engine)


def test_manager_and_admin_can_view_customer_history_but_emp_cannot():
    with database.SessionLocal() as db:
        admin = User(
            username="admin_customer_history_test",
            password_hash=hash_password("Secret123!"),
            full_name="Admin User",
            email="admin_customer_history_test@example.com",
            role="admin",
            is_active=True,
        )
        emp = User(
            username="emp_customer_history_test",
            password_hash=hash_password("Secret123!"),
            full_name="Employee User",
            email="emp_customer_history_test@example.com",
            role="emp",
            is_active=True,
        )
        customer = Customer(phone="0991234567", full_name="John Doe")
        db.add_all([admin, emp, customer])
        db.flush()
        db.add(
            Sale(
                receipt_no="TEST-CH-001",
                customer_id=customer.id,
                customer_name="John Doe",
                subtotal=Decimal("100.00"),
                discount=Decimal("10.00"),
                total=Decimal("90.00"),
                status="PAID",
                created_by=admin.id,
            )
        )
        db.commit()

        admin_token = create_access_token(admin.id, admin.role)
        emp_token = create_access_token(emp.id, emp.role)

    client = TestClient(app)

    manager_resp = client.get(
        f"/api/customers/{customer.id}/history",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert manager_resp.status_code == 200, manager_resp.text
    assert manager_resp.json()["customer"]["phone"] == "0991234567"
    purchase = manager_resp.json()["purchases"][0]
    assert float(purchase["subtotal"]) == 100.0
    assert float(purchase["discount"]) == 10.0
    assert float(purchase["total"]) == 90.0

    emp_resp = client.get(
        f"/api/customers/{customer.id}/history",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert emp_resp.status_code == 403, emp_resp.text


def test_sale_reuses_customer_when_phone_matches_and_keeps_one_record():
    with database.SessionLocal() as db:
        user = User(
            username="customer_match_test",
            password_hash=hash_password("Secret123!"),
            full_name="Cashier",
            email="customer_match_test@example.com",
            role="emp",
            is_active=True,
        )
        existing = Customer(phone="0997777777", full_name="John Doe")
        db.add_all([user, existing])
        db.commit()

        matched = ensure_customer_for_sale(db, "John Smith", "+(099) 777-7777")

        assert matched is not None
        assert matched.id == existing.id
        assert matched.full_name == "John Smith"
        assert db.scalar(select(func.count()).select_from(models.Customer).where(models.Customer.phone == "0997777777")) == 1


def test_usernames_are_case_insensitive_and_dont_duplicate():
    with database.SessionLocal() as db:
        manager = User(
            username="root_manager_case_test",
            password_hash=hash_password("Secret123!"),
            full_name="Manager User",
            email="root_manager_case_test@example.com",
            role="manager",
            is_active=True,
        )
        db.add(manager)
        db.commit()
        manager_token = create_access_token(manager.id, manager.role)

    client = TestClient(app)

    first = client.post(
        "/api/users",
        json={"username": "Manager", "password": "Secret123!", "full_name": "First User", "email": "first_case_test@example.com"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/users",
        json={"username": "manager", "password": "Secret123!", "full_name": "Second User", "email": "second_case_test@example.com"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert second.status_code == 409, second.text


def test_manager_can_update_employee_details():
    with database.SessionLocal() as db:
        manager = User(
            username="manager_update_employee_test",
            password_hash=hash_password("Secret123!"),
            full_name="Manager User",
            email="manager_update_employee_test@example.com",
            role="manager",
            is_active=True,
        )
        emp = User(
            username="emp_to_update_test",
            password_hash=hash_password("Secret123!"),
            full_name="Old Name",
            email="emp_to_update_test@example.com",
            role="emp",
            is_active=True,
        )
        db.add_all([manager, emp])
        db.commit()
        manager_token = create_access_token(manager.id, manager.role)

    client = TestClient(app)
    resp = client.patch(
        f"/api/users/{emp.id}",
        json={"username": "updated_emp_name", "full_name": "Updated Name", "email": "updated_emp_name@example.com"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["username"] == "updated_emp_name"
    assert data["full_name"] == "Updated Name"
    assert data["email"] == "updated_emp_name@example.com"


def test_migrate_legacy_sales_into_customer_records():
    with database.SessionLocal() as db:
        admin = User(
            username="legacy_customer_test",
            password_hash=hash_password("Secret123!"),
            full_name="Legacy Admin",
            email="legacy_customer_test@example.com",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.flush()
        db.add(
            Sale(
                receipt_no="LEGACY-001",
                customer_id=None,
                customer_name="Legacy Buyer",
                subtotal=Decimal("250.00"),
                discount=Decimal("0.00"),
                total=Decimal("250.00"),
                status="PAID",
                created_by=admin.id,
            )
        )
        db.commit()

    database._migrate_sqlite_schema()

    with database.SessionLocal() as db:
        legacy_customer = db.scalar(
            select(models.Customer).where(models.Customer.full_name == "Legacy Buyer")
        )
        sale = db.scalar(select(Sale).where(Sale.receipt_no == "LEGACY-001"))
        assert legacy_customer is not None
        assert sale is not None
        assert sale.customer_id == legacy_customer.id
