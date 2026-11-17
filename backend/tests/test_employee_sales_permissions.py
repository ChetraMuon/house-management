from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
from app.main import app
from app.models import Base, Customer, Sale, User
from app.security import create_access_token, hash_password


database.engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=database.engine)


def test_employee_sales_register_permissions_and_filters():
    with database.SessionLocal() as db:
        manager = User(
            username="manager_employee_sales_test",
            password_hash=hash_password("Secret123!"),
            full_name="Manager User",
            email="manager_employee_sales_test@example.com",
            role="manager",
            is_active=True,
        )
        admin = User(
            username="admin_employee_sales_test",
            password_hash=hash_password("Secret123!"),
            full_name="Admin User",
            email="admin_employee_sales_test@example.com",
            role="admin",
            is_active=True,
        )
        emp = User(
            username="emp_employee_sales_test",
            password_hash=hash_password("Secret123!"),
            full_name="Employee One",
            email="emp_employee_sales_test@example.com",
            role="emp",
            is_active=True,
        )
        other_emp = User(
            username="other_emp_employee_sales_test",
            password_hash=hash_password("Secret123!"),
            full_name="Employee Two",
            email="other_emp_employee_sales_test@example.com",
            role="emp",
            is_active=True,
        )
        customer = Customer(phone="0995551234", full_name="Daily Customer")
        db.add_all([manager, admin, emp, other_emp, customer])
        db.flush()

        db.add_all([
            Sale(
                receipt_no="EMP-SALES-001",
                customer_id=customer.id,
                customer_name="Daily Customer",
                subtotal=Decimal("40.00"),
                discount=Decimal("0.00"),
                total=Decimal("40.00"),
                status="PAID",
                created_by=emp.id,
                created_at=datetime(2024, 1, 15, 10, 0),
            ),
            Sale(
                receipt_no="EMP-SALES-002",
                customer_id=customer.id,
                customer_name="Daily Customer",
                subtotal=Decimal("60.00"),
                discount=Decimal("0.00"),
                total=Decimal("60.00"),
                status="PAID",
                created_by=other_emp.id,
                created_at=datetime(2024, 1, 16, 11, 0),
            ),
        ])
        db.commit()

        manager_token = create_access_token(manager.id, manager.role)
        admin_token = create_access_token(admin.id, admin.role)
        emp_token = create_access_token(emp.id, emp.role)

    client = TestClient(app)

    manager_resp = client.get(
        "/api/sales/employee-sales",
        params={"day": "2024-01-15"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_resp.status_code == 200, manager_resp.text
    data = manager_resp.json()
    assert data["day"] == "2024-01-15"
    assert data["count"] == 1
    assert data["paid_count"] == 1
    assert data["total"] == "40.00"
    row = data["sales"][0]
    assert row["receipt_no"] == "EMP-SALES-001"
    assert row["employee_name"] == "Employee One"
    assert row["customer_name"] == "Daily Customer"
    assert row["customer_phone"] == "0995551234"
    assert any(employee["id"] == emp.id for employee in data["employees"])

    admin_resp = client.get(
        "/api/sales/employee-sales",
        params={"day": "2024-01-15"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_resp.status_code == 200, admin_resp.text

    emp_resp = client.get(
        "/api/sales/employee-sales",
        params={"day": "2024-01-15"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert emp_resp.status_code == 403, emp_resp.text

    employees_resp = client.get(
        "/api/sales/employee-sales/employees",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert employees_resp.status_code == 200, employees_resp.text
    employee_ids = {employee["id"] for employee in employees_resp.json()}
    assert {emp.id, other_emp.id} <= employee_ids
    assert manager.id not in employee_ids
    assert admin.id not in employee_ids

    employees_admin = client.get(
        "/api/sales/employee-sales/employees",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert employees_admin.status_code == 200, employees_admin.text

    employees_emp = client.get(
        "/api/sales/employee-sales/employees",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert employees_emp.status_code == 403, employees_emp.text

    filtered = client.get(
        "/api/sales/employee-sales",
        params={"day": "2024-01-16", "employee_id": other_emp.id, "status": "PAID"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert filtered.status_code == 200, filtered.text
    filtered_data = filtered.json()
    assert filtered_data["count"] == 1
    assert filtered_data["sales"][0]["receipt_no"] == "EMP-SALES-002"
