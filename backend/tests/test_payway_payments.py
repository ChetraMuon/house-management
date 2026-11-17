import base64
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
from app import models, payway
from app.config import settings
from app.main import app
from app.models import Base, Product, Sale, SaleItem, User
from app.routers.sales import _new_tran_id
from app.security import create_access_token, hash_password


database.engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=database.engine)


def _enable_payway(monkeypatch):
    monkeypatch.setattr(settings, "PAYWAY_ENABLED", True)
    monkeypatch.setattr(settings, "PAYWAY_MERCHANT_ID", "test_merchant")
    monkeypatch.setattr(settings, "PAYWAY_API_KEY", "test_key")
    monkeypatch.setattr(settings, "PAYWAY_BASE_URL", "https://payway.invalid")
    monkeypatch.setattr(settings, "PAYWAY_CALLBACK_URL", "")
    monkeypatch.setattr(settings, "PAYWAY_QR_LIFETIME_MINUTES", 10)
    monkeypatch.setattr(settings, "PAYWAY_CURRENCY", "USD")


def _fake_gateway(monkeypatch, state="APPROVED", reference="654321"):
    calls = {}

    def fake_generate_qr(**kwargs):
        calls["tran_id"] = kwargs["tran_id"]
        return {
            "status": {"code": "0", "message": "Success"},
            "qrImage": "data:image/png;base64,ZmFrZS1xcg==",
            "qrString": "000201010212",
            "abapay_deeplink": "abamobilebank://test",
        }

    def fake_check_transaction(tran_id):
        calls["checked"] = tran_id
        return {
            "status": {"code": "00", "message": "Success!"},
            "data": {
                "payment_status": state,
                "payment_status_code": 0 if state == "APPROVED" else 2,
                "apv": reference,
                "payment_amount": 25.0,
            },
        }

    monkeypatch.setattr(payway, "generate_qr", fake_generate_qr)
    monkeypatch.setattr(payway, "check_transaction", fake_check_transaction)
    monkeypatch.setattr(payway, "close_transaction", lambda tran_id: {"status": {"code": "00"}})
    monkeypatch.setattr("app.routers.sales.send_stock_notification", lambda *a, **k: True)
    monkeypatch.setattr("app.routers.sales.send_low_stock_notification", lambda *a, **k: True)
    calls["paid_alerts"] = []
    monkeypatch.setattr(
        "app.routers.sales.send_sale_paid_notification",
        lambda **kwargs: calls["paid_alerts"].append(kwargs) or True,
    )
    return calls


def _seed_sale(stock=10, qty=2):
    unique = uuid4().hex[:8]
    with database.SessionLocal() as db:
        emp = User(
            username=f"payway_emp_{unique}",
            password_hash=hash_password("Secret123!"),
            full_name="PayWay Cashier",
            email=f"payway_emp_{unique}@example.com",
            role="emp",
            is_active=True,
        )
        other = User(
            username=f"payway_other_{unique}",
            password_hash=hash_password("Secret123!"),
            full_name="Other Cashier",
            email=f"payway_other_{unique}@example.com",
            role="emp",
            is_active=True,
        )
        manager = User(
            username=f"payway_mgr_{unique}",
            password_hash=hash_password("Secret123!"),
            full_name="PayWay Manager",
            email=f"payway_mgr_{unique}@example.com",
            role="manager",
            is_active=True,
        )
        product = Product(
            sku=f"PAYWAY-{unique}",
            name="QR Test Item",
            unit="pcs",
            price=Decimal("12.50"),
            cost=Decimal("6.00"),
            stock_qty=stock,
            min_stock=2,
            is_active=True,
        )
        db.add_all([emp, other, manager, product])
        db.flush()
        sale = Sale(
            receipt_no=f"PAYWAY-{unique}",
            subtotal=Decimal("25.00"),
            discount=Decimal("0.00"),
            total=Decimal("25.00"),
            status="READY",
            requires_approval=False,
            created_by=emp.id,
        )
        sale.items = [
            SaleItem(
                product_id=product.id,
                product_name=product.name,
                unit_price=Decimal("12.50"),
                quantity=qty,
                line_total=Decimal("25.00"),
            )
        ]
        db.add(sale)
        db.commit()
        return emp.id, other.id, manager.id, product.id, sale.id


def _payment(sale_id):
    with database.SessionLocal() as db:
        return db.scalar(select(models.Payment).where(models.Payment.sale_id == sale_id))


def test_payway_qr_reserves_stock_and_status_confirms_sale(monkeypatch):
    _enable_payway(monkeypatch)
    calls = _fake_gateway(monkeypatch)
    emp_id, _, _, product_id, sale_id = _seed_sale()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}

    qr_response = client.post(f"/api/sales/{sale_id}/payway/qr", headers=headers)
    assert qr_response.status_code == 200, qr_response.text
    qr = qr_response.json()
    assert qr["status"] == "PENDING"
    assert qr["tran_id"] == calls["tran_id"]
    assert qr["qr_image"].startswith("data:image/png")
    assert datetime.fromisoformat(qr["expires_at"]).tzinfo is not None

    with database.SessionLocal() as db:
        assert db.get(Product, product_id).stock_qty == 8
        assert db.get(Sale, sale_id).status == "READY"
    payment = _payment(sale_id)
    assert payment.status == "PENDING"
    assert payment.provider == "PAYWAY"
    assert payment.stock_reserved is True

    status_response = client.get(f"/api/sales/{sale_id}/payway/status", headers=headers)
    assert status_response.status_code == 200, status_response.text
    body = status_response.json()
    assert body["status"] == "SUCCEEDED"
    assert body["sale_status"] == "PAID"
    assert body["sale"]["status"] == "PAID"
    assert calls["checked"] == qr["tran_id"]
    assert len(calls["paid_alerts"]) == 1
    assert calls["paid_alerts"][0]["payment_label"] == "ABA QR"

    with database.SessionLocal() as db:
        # The reservation is not deducted a second time on confirmation.
        assert db.get(Product, product_id).stock_qty == 8
        assert db.get(Sale, sale_id).status == "PAID"
    payment = _payment(sale_id)
    assert payment.status == "SUCCEEDED"
    assert payment.provider_ref == "654321"
    assert payment.amount_received == Decimal("25.00")

    receipt = client.get(f"/api/sales/{sale_id}/receipt", headers=headers)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["payment_provider"] == "PAYWAY"
    assert receipt.json()["payment_reference"] == "654321"


def test_payway_cancel_restores_reserved_stock(monkeypatch):
    _enable_payway(monkeypatch)
    _fake_gateway(monkeypatch, state="PENDING")
    emp_id, _, _, product_id, sale_id = _seed_sale()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}

    assert client.post(f"/api/sales/{sale_id}/payway/qr", headers=headers).status_code == 200
    with database.SessionLocal() as db:
        assert db.get(Product, product_id).stock_qty == 8

    cancel = client.post(f"/api/sales/{sale_id}/payway/cancel", headers=headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"

    with database.SessionLocal() as db:
        assert db.get(Product, product_id).stock_qty == 10
        assert db.get(Sale, sale_id).status == "READY"
    payment = _payment(sale_id)
    assert payment.status == "CANCELLED"
    assert payment.stock_reserved is False


def test_payway_late_webhook_after_cancel_completes_sale(monkeypatch):
    """A customer may pay just before the QR is closed. The late callback must
    still verify the payment, mark the sale paid, and re-deduct stock."""
    _enable_payway(monkeypatch)
    gateway = {"state": "PENDING"}
    calls = {}

    def fake_generate_qr(**kwargs):
        calls["tran_id"] = kwargs["tran_id"]
        return {
            "status": {"code": "0", "message": "Success"},
            "qrImage": "data:image/png;base64,ZmFrZS1xcg==",
        }

    def fake_check_transaction(tran_id):
        return {
            "status": {"code": "00", "message": "Success!"},
            "data": {
                "payment_status": gateway["state"],
                "payment_status_code": 0 if gateway["state"] == "APPROVED" else 2,
                "apv": "LATE-REF",
                "payment_amount": 25.0,
            },
        }

    monkeypatch.setattr(payway, "generate_qr", fake_generate_qr)
    monkeypatch.setattr(payway, "check_transaction", fake_check_transaction)
    monkeypatch.setattr(payway, "close_transaction", lambda tran_id: {"status": {"code": "00"}})
    monkeypatch.setattr("app.routers.sales.send_stock_notification", lambda *a, **k: True)
    monkeypatch.setattr("app.routers.sales.send_low_stock_notification", lambda *a, **k: True)

    emp_id, _, _, product_id, sale_id = _seed_sale()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}

    qr = client.post(f"/api/sales/{sale_id}/payway/qr", headers=headers).json()
    cancel = client.post(f"/api/sales/{sale_id}/payway/cancel", headers=headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"

    with database.SessionLocal() as db:
        assert db.get(Product, product_id).stock_qty == 10
        assert db.get(Sale, sale_id).status == "READY"
    assert _payment(sale_id).status == "CANCELLED"

    # The payment lands at PayWay after the local cancel.
    gateway["state"] = "APPROVED"
    webhook = client.post(
        "/api/payments/payway/webhook",
        json={"merchant_ref": qr["tran_id"], "payment_status": "APPROVED"},
    )
    assert webhook.status_code == 200, webhook.text
    assert webhook.json()["payment_status"] == "SUCCEEDED"

    with database.SessionLocal() as db:
        assert db.get(Sale, sale_id).status == "PAID"
        # Stock is reserved again because the sale really was paid.
        assert db.get(Product, product_id).stock_qty == 8
    payment = _payment(sale_id)
    assert payment.status == "SUCCEEDED"
    assert payment.stock_reserved is True
    assert payment.provider_ref == "LATE-REF"


def test_payway_qr_replacement_detects_late_payment(monkeypatch):
    _enable_payway(monkeypatch)
    gateway = {"state": "PENDING"}

    def fake_generate_qr(**kwargs):
        return {
            "status": {"code": "0", "message": "Success"},
            "qrImage": "data:image/png;base64,ZmFrZS1xcg==",
        }

    def fake_check_transaction(tran_id):
        return {
            "status": {"code": "00", "message": "Success!"},
            "data": {
                "payment_status": gateway["state"],
                "payment_status_code": 0 if gateway["state"] == "APPROVED" else 2,
                "apv": "LATE-REF",
                "payment_amount": 25.0,
            },
        }

    monkeypatch.setattr(payway, "generate_qr", fake_generate_qr)
    monkeypatch.setattr(payway, "check_transaction", fake_check_transaction)
    monkeypatch.setattr(payway, "close_transaction", lambda tran_id: {"status": {"code": "00"}})
    monkeypatch.setattr("app.routers.sales.send_stock_notification", lambda *a, **k: True)
    monkeypatch.setattr("app.routers.sales.send_low_stock_notification", lambda *a, **k: True)

    emp_id, _, _, product_id, sale_id = _seed_sale()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}

    first = client.post(f"/api/sales/{sale_id}/payway/qr", headers=headers)
    assert first.status_code == 200, first.text
    assert client.post(f"/api/sales/{sale_id}/payway/cancel", headers=headers).status_code == 200

    # The customer paid the cancelled QR; a replacement must not be issued.
    gateway["state"] = "APPROVED"
    replacement = client.post(f"/api/sales/{sale_id}/payway/qr", headers=headers)
    assert replacement.status_code == 409, replacement.text

    with database.SessionLocal() as db:
        assert db.get(Sale, sale_id).status == "PAID"
        assert db.get(Product, product_id).stock_qty == 8
    assert _payment(sale_id).status == "SUCCEEDED"


def test_payway_webhook_verifies_with_gateway(monkeypatch):
    _enable_payway(monkeypatch)
    _fake_gateway(monkeypatch)
    emp_id, _, _, _, sale_id = _seed_sale()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}

    qr = client.post(f"/api/sales/{sale_id}/payway/qr", headers=headers).json()

    ignored = client.post(
        "/api/payments/payway/webhook",
        json={"merchant_ref": "unknown-reference", "payment_status": "APPROVED"},
    )
    assert ignored.status_code == 200
    assert ignored.json()["status"] == "ignored"

    webhook = client.post(
        "/api/payments/payway/webhook",
        json={"merchant_ref": qr["tran_id"], "payment_status": "APPROVED"},
    )
    assert webhook.status_code == 200, webhook.text
    assert webhook.json()["payment_status"] == "SUCCEEDED"

    with database.SessionLocal() as db:
        assert db.get(Sale, sale_id).status == "PAID"
    assert _payment(sale_id).status == "SUCCEEDED"


def test_payway_permissions_and_disabled_flag(monkeypatch):
    _enable_payway(monkeypatch)
    _fake_gateway(monkeypatch)
    emp_id, other_id, manager_id, _, sale_id = _seed_sale()

    client = TestClient(app)
    emp_headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(other_id, 'emp')}"}
    manager_headers = {"Authorization": f"Bearer {create_access_token(manager_id, 'manager')}"}

    assert client.post(f"/api/sales/{sale_id}/payway/qr", headers=other_headers).status_code == 403
    assert client.post(f"/api/sales/{sale_id}/payway/qr", headers=manager_headers).status_code == 403

    monkeypatch.setattr(settings, "PAYWAY_ENABLED", False)
    assert client.post(f"/api/sales/{sale_id}/payway/qr", headers=emp_headers).status_code == 503

    config = client.get("/api/payments/config", headers=emp_headers)
    assert config.status_code == 200
    assert config.json()["payway_enabled"] is False


def test_payway_hash_is_hmac_sha512(monkeypatch):
    monkeypatch.setattr(settings, "PAYWAY_API_KEY", "secret")
    expected = base64.b64encode(
        hmac.new(b"secret", b"20240101000000merchant123", hashlib.sha512).digest()
    ).decode("ascii")
    assert payway._hash(["20240101000000", "merchant", "123"]) == expected


def test_payway_sandbox_detection(monkeypatch):
    monkeypatch.setattr(settings, "PAYWAY_BASE_URL", "https://checkout-sandbox.payway.com.kh")
    assert payway.is_sandbox() is True
    monkeypatch.setattr(settings, "PAYWAY_BASE_URL", "https://checkout.payway.com.kh")
    assert payway.is_sandbox() is False


def test_generate_qr_signs_fields_in_documented_order(monkeypatch):
    _enable_payway(monkeypatch)
    captured = {}

    def fake_post(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {
            "status": {"code": "0", "message": "Success"},
            "qrImage": "data:image/png;base64,ZmFrZQ==",
        }

    monkeypatch.setattr(payway, "_post", fake_post)
    payway.generate_qr(
        tran_id="T123456",
        amount=Decimal("12.50"),
        items=[{"name": "Item A", "quantity": 2, "price": Decimal("6.25")}],
        lifetime_minutes=10,
    )

    payload = captured["payload"]
    assert captured["path"] == "/api/payment-gateway/v1/payments/generate-qr"
    # Exact order from the QR API docs (currency comes before custom_fields).
    b4hash = "".join([
        payload["req_time"],
        payload["merchant_id"],
        payload["tran_id"],
        payload["amount"],
        payload["items"],
        "", "", "", "",  # first_name, last_name, email, phone
        payload["purchase_type"],
        payload["payment_option"],
        "",  # callback_url
        "",  # return_deeplink
        payload["currency"],
        "", "", "",  # custom_fields, return_params, payout
        str(payload["lifetime"]),
        payload["qr_image_template"],
    ])
    expected = base64.b64encode(
        hmac.new(b"test_key", b4hash.encode("utf-8"), hashlib.sha512).digest()
    ).decode("ascii")
    assert payload["hash"] == expected


def test_items_payload_respects_payway_length_limit():
    items = [
        {"name": "X" * 100, "quantity": 2, "price": Decimal("1.25")}
        for _ in range(10)
    ]
    encoded = payway._items_payload(items)
    assert len(encoded) <= 500
    assert json.loads(base64.b64decode(encoded))


def test_tran_id_fits_payway_limit_and_is_unique():
    ids = {_new_tran_id(123) for _ in range(100)}
    assert len(ids) == 100
    assert all(len(tran_id) <= 20 for tran_id in ids)


def _enable_simulator(monkeypatch):
    _enable_payway(monkeypatch)
    monkeypatch.setattr(settings, "PAYWAY_BASE_URL", "https://checkout-sandbox.payway.com.kh")
    monkeypatch.setattr(settings, "PAYWAY_SIMULATOR_ENABLED", True)


def test_payway_simulator_marks_pending_sandbox_sale_paid(monkeypatch):
    _enable_simulator(monkeypatch)
    calls = _fake_gateway(monkeypatch, state="PENDING")
    emp_id, other_id, manager_id, product_id, sale_id = _seed_sale()

    client = TestClient(app)
    emp_headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}
    manager_headers = {"Authorization": f"Bearer {create_access_token(manager_id, 'manager')}"}

    config = client.get("/api/payments/config", headers=emp_headers)
    assert config.status_code == 200
    assert config.json()["sandbox"] is True
    assert config.json()["simulator_enabled"] is True

    qr = client.post(f"/api/sales/{sale_id}/payway/qr", headers=emp_headers)
    assert qr.status_code == 200, qr.text

    # Employees cannot use the management-only test payer.
    assert client.get("/api/payway-simulator/pending", headers=emp_headers).status_code == 403
    assert client.post(
        f"/api/payway-simulator/{sale_id}/pay", headers=emp_headers
    ).status_code == 403

    pending = client.get("/api/payway-simulator/pending", headers=manager_headers)
    assert pending.status_code == 200, pending.text
    rows = pending.json()
    assert any(row["sale_id"] == sale_id and row["tran_id"] == qr.json()["tran_id"] for row in rows)

    pay = client.post(f"/api/payway-simulator/{sale_id}/pay", headers=manager_headers)
    assert pay.status_code == 200, pay.text
    body = pay.json()
    assert body["status"] == "SUCCEEDED"
    assert body["sale_status"] == "PAID"
    assert body["sale"]["status"] == "PAID"
    assert "No real money moved" in body["message"]

    with database.SessionLocal() as db:
        assert db.get(Sale, sale_id).status == "PAID"
        # The QR already reserved stock; confirming must not deduct it again.
        assert db.get(Product, product_id).stock_qty == 8
        audit_row = db.scalar(
            select(models.AuditLog).where(
                models.AuditLog.action == "PAYWAY_SIMULATED",
                models.AuditLog.entity_id == str(sale_id),
            )
        )
        assert audit_row is not None
        assert "Simulated sandbox PayWay payment" in audit_row.detail

    payment = _payment(sale_id)
    assert payment.status == "SUCCEEDED"
    assert payment.provider_ref == "SIMULATED"
    assert payment.amount_received == Decimal("25.00")
    assert json.loads(payment.raw_response)["data"]["simulated"] is True

    # Idempotent: a second click does not create a second payment.
    again = client.post(f"/api/payway-simulator/{sale_id}/pay", headers=manager_headers)
    assert again.status_code == 200
    assert again.json()["status"] == "SUCCEEDED"
    assert len(calls["paid_alerts"]) == 1
    assert calls["paid_alerts"][0]["payment_label"] == "ABA QR"

    assert not any(
        row["sale_id"] == sale_id
        for row in client.get("/api/payway-simulator/pending", headers=manager_headers).json()
    )


def test_payway_simulator_is_sandbox_only_and_can_be_disabled(monkeypatch):
    _enable_payway(monkeypatch)
    _fake_gateway(monkeypatch, state="PENDING")
    emp_id, _, manager_id, _, sale_id = _seed_sale()
    client = TestClient(app)
    emp_headers = {"Authorization": f"Bearer {create_access_token(emp_id, 'emp')}"}
    manager_headers = {"Authorization": f"Bearer {create_access_token(manager_id, 'manager')}"}
    assert client.post(f"/api/sales/{sale_id}/payway/qr", headers=emp_headers).status_code == 200

    # Production URL: the simulator must stay hidden even if the flag is on.
    monkeypatch.setattr(settings, "PAYWAY_SIMULATOR_ENABLED", True)
    assert client.get("/api/payway-simulator/pending", headers=manager_headers).status_code == 404
    assert client.post(
        f"/api/payway-simulator/{sale_id}/pay", headers=manager_headers
    ).status_code == 404

    # Sandbox URL but the flag is off: still hidden.
    monkeypatch.setattr(settings, "PAYWAY_BASE_URL", "https://checkout-sandbox.payway.com.kh")
    monkeypatch.setattr(settings, "PAYWAY_SIMULATOR_ENABLED", False)
    config = client.get("/api/payments/config", headers=emp_headers)
    assert config.json()["simulator_enabled"] is False
    assert client.get("/api/payway-simulator/pending", headers=manager_headers).status_code == 404
