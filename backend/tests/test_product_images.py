from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
import app.routers.products as products_router
from app.main import app
from app.models import Base, Product, User
from app.security import create_access_token


@pytest.fixture
def product_image_client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", test_sessions)
    monkeypatch.setattr(products_router.settings, "PRODUCT_IMAGE_DIR", str(tmp_path))
    static_mount = next(route for route in app.routes if route.name == "product-images")
    monkeypatch.setattr(static_mount.app, "directory", str(tmp_path))
    monkeypatch.setattr(static_mount.app, "all_directories", [str(tmp_path)])
    Base.metadata.create_all(bind=engine)

    unique = uuid4().hex[:8]
    with test_sessions() as db:
        manager = User(
            username=f"image_mgr_{unique}",
            password_hash="hash",
            full_name="Image Manager",
            role="manager",
            is_active=True,
        )
        employee = User(
            username=f"image_emp_{unique}",
            password_hash="hash",
            full_name="Image Employee",
            role="emp",
            is_active=True,
        )
        product = Product(
            sku=f"IMAGE-{unique}",
            name="Sample product",
            unit="pcs",
            price=Decimal("10.00"),
            cost=Decimal("5.00"),
            stock_qty=1,
            min_stock=1,
        )
        db.add_all([manager, employee, product])
        db.flush()
        manager_token = create_access_token(manager.id, manager.role)
        employee_token = create_access_token(employee.id, employee.role)
        product_id = product.id
        db.commit()

    with TestClient(app) as client:
        yield client, tmp_path, product_id, manager_token, employee_token

    engine.dispose()


def test_manager_can_upload_product_image_and_invalid_upload_is_rejected(product_image_client):
    client, image_dir, product_id, manager_token, _ = product_image_client
    headers = {"Authorization": f"Bearer {manager_token}"}
    png = b"\x89PNG\r\n\x1a\n" + b"test-image"

    response = client.put(
        f"/api/products/{product_id}/image",
        files={"image": ("sample.png", png, "image/png")},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    image_url = response.json()["image_url"]
    assert image_url.startswith("/uploads/products/")
    image_path = image_dir / image_url.rsplit("/", 1)[-1]
    assert image_path.read_bytes() == png
    served_image = client.get(image_url)
    assert served_image.status_code == 200
    assert served_image.content == png

    invalid = client.put(
        f"/api/products/{product_id}/image",
        files={"image": ("not-an-image.png", b"not an image", "image/png")},
        headers=headers,
    )
    assert invalid.status_code == 415
    assert client.get("/api/products", headers=headers).json()[0]["image_url"] == image_url


def test_only_manager_can_upload_product_image(product_image_client):
    client, _, product_id, _, employee_token = product_image_client
    response = client.put(
        f"/api/products/{product_id}/image",
        files={"image": ("sample.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 403


def test_product_image_upload_enforces_size_limit(product_image_client):
    client, _, product_id, manager_token, _ = product_image_client
    response = client.put(
        f"/api/products/{product_id}/image",
        files={"image": ("large.png", b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024), "image/png")},
        headers={"Authorization": f"Bearer {manager_token}"},
    )

    assert response.status_code == 413
