from decimal import Decimal
from datetime import datetime
from uuid import uuid4
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
from app import models, telegram
from app.database import init_db
from app.models import Base
from app.telegram import (
    build_approval_message,
    build_low_stock_message,
    build_sale_paid_message,
    build_stock_message,
    send_approval_notification,
    send_low_stock_notification,
    send_sale_paid_notification,
    send_stock_notification,
)
from app.routers.products import delete_product, update_product
from app.routers.sales import checkout, ensure_customer_for_sale
from app import schemas


# Keep this test module off the real application database. Several tests below
# call service functions that commit internally.
database.engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=database.engine)


def test_ensure_customer_for_sale_creates_and_tracks_phone():
    init_db()
    phone = "0991234567"
    db = database.SessionLocal()
    try:
        customer = ensure_customer_for_sale(db, "Alice", phone)
        assert customer is not None
        assert customer.phone == phone
        assert db.get(models.Customer, customer.id) is not None
    finally:
        db.rollback()
        db.close()


def test_build_approval_message_includes_details():
    text = build_approval_message("APPROVED", "INV-1024", 12000, "admin", "High-value sale")
    assert "APPROVAL" in text.upper()
    assert "INV-1024" in text
    assert "12000" in text
    assert "admin" in text


def test_build_low_stock_message_includes_details():
    text = build_low_stock_message("Desk Lamp", 2, 5, "manager")
    assert "LOW STOCK" in text.upper()
    assert "Desk Lamp" in text
    assert "2" in text
    assert "5" in text


def test_build_stock_message_includes_details():
    text = build_stock_message("IN", "Sofa 3-seater", 12, "manager", 45, "PO-1001", "Restock")
    assert "STOCK IN" in text.upper()
    assert "Sofa 3-seater" in text
    assert "12" in text
    assert "manager" in text
    assert "45" in text


def test_build_sale_paid_message_includes_details():
    text = build_sale_paid_message(
        "R20260101-000001",
        75.5,
        "ABA QR",
        "Cashier One",
        "Alice",
        "0991234567",
        datetime(2026, 1, 1, 9, 30),
    )
    assert "SALE PAID" in text.upper()
    assert "R20260101-000001" in text
    assert "75.50" in text
    assert "ABA QR" in text
    assert "Cashier One" in text
    assert "Alice" in text
    assert "0991234567" in text
    assert "2026-01-01 09:30" in text


def test_build_sale_paid_message_without_customer():
    text = build_sale_paid_message("R1-000002", 10, "Cash", "Cashier One")
    assert "Customer:" not in text
    assert "Phone:" not in text


def test_update_product_and_delete_unused_product():
    db = database.SessionLocal()
    try:
        manager = models.User(
            username=f"prod_mgr_{uuid4().hex[:8]}",
            password_hash="hash",
            full_name="Product Manager",
            email=f"prod_mgr_{uuid4().hex[:8]}@example.com",
            role="manager",
            is_active=True,
        )
        product = models.Product(
            sku=f"EDIT-DEL-{uuid4().hex[:8]}",
            name="Old Lamp",
            unit="pcs",
            price=Decimal("10.00"),
            cost=Decimal("6.00"),
            stock_qty=0,
            min_stock=3,
            is_active=True,
        )
        db.add_all([manager, product])
        db.flush()

        updated = update_product(
            product.id,
            schemas.ProductUpdate(sku=f"NEW-{uuid4().hex[:6]}", name="Updated Lamp", min_stock=5),
            db=db,
            user=manager,
        )
        assert updated.name == "Updated Lamp"
        assert updated.min_stock == 5
        assert updated.can_delete is True

        deleted = delete_product(product.id, db=db, user=manager)
        assert deleted.can_delete is True
        assert db.get(models.Product, product.id) is None
    finally:
        db.rollback()
        db.close()


def test_delete_product_with_stock_is_blocked_and_can_be_archived():
    db = database.SessionLocal()
    try:
        manager = models.User(
            username=f"prod_mgr_{uuid4().hex[:8]}",
            password_hash="hash",
            full_name="Product Manager",
            email=f"prod_mgr_{uuid4().hex[:8]}@example.com",
            role="manager",
            is_active=True,
        )
        product = models.Product(
            sku=f"ARCHIVE-{uuid4().hex[:8]}",
            name="Stocked Lamp",
            unit="pcs",
            price=Decimal("10.00"),
            cost=Decimal("6.00"),
            stock_qty=2,
            min_stock=3,
            is_active=True,
        )
        db.add_all([manager, product])
        db.flush()

        with pytest.raises(HTTPException) as exc:
            delete_product(product.id, db=db, user=manager)
        assert exc.value.status_code == 409
        assert db.get(models.Product, product.id) is not None

        archived = update_product(
            product.id,
            schemas.ProductUpdate(is_active=False),
            db=db,
            user=manager,
        )
        assert archived.is_active is False
        assert archived.can_delete is False

        restored = update_product(
            product.id,
            schemas.ProductUpdate(is_active=True),
            db=db,
            user=manager,
        )
        assert restored.is_active is True
    finally:
        db.rollback()
        db.close()


def test_delete_product_with_history_is_blocked():
    db = database.SessionLocal()
    try:
        manager = models.User(
            username=f"prod_mgr_{uuid4().hex[:8]}",
            password_hash="hash",
            full_name="Product Manager",
            email=f"prod_mgr_{uuid4().hex[:8]}@example.com",
            role="manager",
            is_active=True,
        )
        product = models.Product(
            sku=f"HISTORY-{uuid4().hex[:8]}",
            name="Historic Lamp",
            unit="pcs",
            price=Decimal("10.00"),
            cost=Decimal("6.00"),
            stock_qty=0,
            min_stock=0,
            is_active=True,
        )
        db.add_all([manager, product])
        db.flush()
        db.add(models.StockMovement(
            product_id=product.id,
            movement_type="IN",
            quantity=1,
            qty_before=0,
            qty_after=1,
            reference="TEST",
            created_by=manager.id,
        ))
        db.flush()

        with pytest.raises(HTTPException) as exc:
            delete_product(product.id, db=db, user=manager)
        assert exc.value.status_code == 409
        assert db.get(models.Product, product.id) is not None
    finally:
        db.rollback()
        db.close()


def test_checkout_sends_stock_out_notification_for_sale():
    db = database.SessionLocal()
    try:
        unique = uuid4().hex[:8]
        cashier = models.User(
            username=f"checkout_notify_{unique}",
            password_hash="hash",
            full_name="Cashier",
            email=f"checkout_notify_{unique}@example.com",
            role="emp",
            is_active=True,
        )
        product = models.Product(
            sku=f"STOCK-OUT-{unique}",
            name="Desk Lamp",
            unit="pcs",
            price=Decimal("25.00"),
            cost=Decimal("15.00"),
            stock_qty=5,
            min_stock=3,
            is_active=True,
        )
        db.add_all([cashier, product])
        db.flush()
        sale = models.Sale(
            receipt_no=f"SALE-NOTIFY-{unique}",
            subtotal=Decimal("75.00"),
            discount=Decimal("0.00"),
            total=Decimal("75.00"),
            status="READY",
            requires_approval=False,
            created_by=cashier.id,
            customer_name="Alice",
        )
        sale.items = [models.SaleItem(product_id=product.id, product_name=product.name, unit_price=product.price, quantity=3, line_total=Decimal("75.00"))]
        db.add(sale)
        db.commit()

        with patch("app.routers.sales.send_stock_notification") as mock_stock, \
             patch("app.routers.sales.send_low_stock_notification") as mock_low, \
             patch("app.routers.sales.send_sale_paid_notification") as mock_paid:
            checkout(sale.id, schemas.CheckoutIn(method="CASH", amount_received=Decimal("75.00")), db=db, user=cashier)

        assert mock_stock.call_count >= 1
        assert mock_stock.call_args[0][0] == "OUT"
        assert mock_low.call_count >= 1
        mock_paid.assert_called_once()
        paid = mock_paid.call_args.kwargs
        assert paid["receipt_no"] == sale.receipt_no
        assert paid["payment_label"] == "Cash"
        assert paid["cashier_name"] == "Cashier"
        assert paid["customer_name"] == "Alice"
    finally:
        db.rollback()
        db.close()


def test_send_sale_paid_notification_uses_telegram_api():
    with patch.object(telegram.settings, "TELEGRAM_BOT_TOKEN", "abc123"), \
         patch.object(telegram.settings, "TELEGRAM_CHAT_ID", "-100999"), \
         patch("app.telegram.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = b"{\"ok\": true}"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = send_sale_paid_notification(
            "R20260101-000001",
            75,
            "ABA QR",
            "Cashier One",
            customer_name="Alice",
        )

        assert result is True
        mock_urlopen.assert_called_once()
        payload = mock_urlopen.call_args.args[0].data.decode("utf-8")
        assert "SALE PAID" in payload
        assert "R20260101-000001" in payload
        assert "ABA QR" in payload


def test_send_stock_notification_uses_telegram_api():
    with patch.object(telegram.settings, "TELEGRAM_BOT_TOKEN", "abc123"), \
         patch.object(telegram.settings, "TELEGRAM_CHAT_ID", "-100999"), \
         patch("app.telegram.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = b"{\"ok\": true}"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = send_stock_notification(
            "OUT",
            "Sofa 3-seater",
            3,
            "manager",
            reference="SO-99",
            note="Sold to customer",
        )

        assert result is True
        mock_urlopen.assert_called_once()


def test_send_low_stock_notification_uses_telegram_api():
    with patch.object(telegram.settings, "TELEGRAM_BOT_TOKEN", "abc123"), \
         patch.object(telegram.settings, "TELEGRAM_CHAT_ID", "-100999"), \
         patch("app.telegram.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = b"{\"ok\": true}"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = send_low_stock_notification("Desk Lamp", 2, 5)

        assert result is True
        mock_urlopen.assert_called_once()


def test_send_approval_notification_uses_telegram_api():
    with patch.object(telegram.settings, "TELEGRAM_BOT_TOKEN", "abc123"), \
         patch.object(telegram.settings, "TELEGRAM_CHAT_ID", "-100999"), \
         patch("app.telegram.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = b"{\"ok\": true}"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        result = send_approval_notification("APPROVED", "INV-1024", 12000, "admin", "Approved for customer")

        assert result is True
        mock_urlopen.assert_called_once()
