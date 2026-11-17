from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import audit, get_current_user, require_roles
from ..telegram import send_low_stock_notification

router = APIRouter(tags=["products"])
manager_only = require_roles("manager")
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024


def _image_extension(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    return None


def _remove_image(image_url: str | None) -> None:
    if not image_url:
        return
    image_path = Path(settings.PRODUCT_IMAGE_DIR) / Path(image_url).name
    try:
        image_path.unlink()
    except FileNotFoundError:
        pass


def _used_product_ids(db: Session) -> set[int]:
    """Products referenced by sales or stock history cannot be hard-deleted."""
    used = set(db.scalars(select(models.SaleItem.product_id).distinct()).all())
    used.update(db.scalars(select(models.StockMovement.product_id).distinct()).all())
    return used


def _can_delete(product: models.Product, used_ids: set[int]) -> bool:
    return product.stock_qty == 0 and product.id not in used_ids


@router.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    return db.scalars(select(models.Category).order_by(models.Category.name)).all()


@router.post("/categories", response_model=schemas.CategoryOut, status_code=201)
def create_category(data: schemas.CategoryIn, db: Session = Depends(get_db), user=Depends(manager_only)):
    cat = models.Category(name=data.name.strip())
    db.add(cat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Category already exists")
    return cat


@router.get("/products", response_model=list[schemas.ProductOut])
def list_products(
    q: str | None = Query(None, description="search name or SKU"),
    only_active: bool = True,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    stmt = select(models.Product).order_by(models.Product.name)
    if only_active:
        stmt = stmt.where(models.Product.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(models.Product.name.like(like), models.Product.sku.like(like)))
    products = db.scalars(stmt).all()
    used_ids = _used_product_ids(db)
    for product in products:
        product.can_delete = _can_delete(product, used_ids)
    return products


@router.post("/products", response_model=schemas.ProductOut, status_code=201)
def create_product(data: schemas.ProductIn, request: Request = None, db: Session = Depends(get_db),
                   user=Depends(manager_only)):
    product = models.Product(**data.model_dump(), stock_qty=0)
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "SKU already exists")
    audit(db, user.id, "PRODUCT_CREATED", "product", product.id, product.sku,
          request=request, username=user.username)
    db.commit()
    product.can_delete = True
    if product.stock_qty <= product.min_stock:
        send_low_stock_notification(product.name, product.stock_qty, product.min_stock, user.full_name or user.username)
    return product


@router.patch("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int, data: schemas.ProductUpdate, request: Request = None,
    db: Session = Depends(get_db), user=Depends(manager_only),
):
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    changes = data.model_dump(exclude_unset=True)
    was_active = product.is_active
    try:
        for field, value in changes.items():
            setattr(product, field, value)
        if "is_active" in changes and product.is_active != was_active:
            action = "PRODUCT_RESTORED" if product.is_active else "PRODUCT_ARCHIVED"
            audit(db, user.id, action, "product", product.id, product.sku,
                  request=request, username=user.username)
        else:
            audit(db, user.id, "PRODUCT_UPDATED", "product", product.id,
                  request=request, username=user.username)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "SKU already exists")
    product.can_delete = _can_delete(product, _used_product_ids(db))
    if product.stock_qty <= product.min_stock:
        send_low_stock_notification(product.name, product.stock_qty, product.min_stock, user.full_name or user.username)
    return product


@router.put("/products/{product_id}/image", response_model=schemas.ProductOut)
def upload_product_image(
    product_id: int,
    request: Request = None,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(manager_only),
):
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")

    content = image.file.read(MAX_PRODUCT_IMAGE_BYTES + 1)
    if len(content) > MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(413, "Product images must be 5 MB or smaller")

    extension = _image_extension(content)
    if extension is None:
        raise HTTPException(415, "Upload a PNG, JPEG, GIF, or WebP image")

    image_dir = Path(settings.PRODUCT_IMAGE_DIR)
    filename = f"{uuid4().hex}{extension}"
    image_path = image_dir / filename
    try:
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(500, "Could not save product image") from exc

    previous_image = product.image_url
    image_url = f"/uploads/products/{filename}"
    product.image_url = image_url
    audit(db, user.id, "PRODUCT_IMAGE_UPDATED", "product", product.id, product.sku,
          request=request, username=user.username)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        _remove_image(image_url)
        raise HTTPException(500, "Could not save product image") from exc

    _remove_image(previous_image)
    product.can_delete = _can_delete(product, _used_product_ids(db))
    return product


@router.delete("/products/{product_id}", response_model=schemas.ProductOut)
def delete_product(
    product_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    user=Depends(manager_only),
):
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    if not _can_delete(product, _used_product_ids(db)):
        raise HTTPException(
            409,
            "This product has stock or sales history. Archive it instead of deleting.",
        )

    image_url = product.image_url
    audit(db, user.id, "PRODUCT_DELETED", "product", product.id, product.sku,
          request=request, username=user.username)
    db.delete(product)
    db.commit()
    _remove_image(image_url)
    product.can_delete = True
    return product
