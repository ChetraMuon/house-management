"""User management - MANAGER only.
Manager can create employees and promote emp -> admin (or demote admin -> emp)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import audit, require_roles
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])
manager_only = require_roles("manager")


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _: models.User = Depends(manager_only)):
    return db.scalars(select(models.User).order_by(models.User.id)).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_employee(
    data: schemas.UserCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    """New accounts are always created as `emp`; promote afterwards via PATCH /users/{id}/role."""
    username = data.username.strip().lower()
    email = (data.email or "").strip().lower() or None

    if db.scalar(select(models.User).where(func.lower(models.User.username) == username)):
        raise HTTPException(409, "Username already exists")
    if email and db.scalar(select(models.User).where(func.lower(models.User.email) == email)):
        raise HTTPException(409, "Email already exists")

    user = models.User(
        username=username,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        email=email,
        role="emp",
        created_by=manager.id,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username or email already exists")
    audit(db, manager.id, "USER_CREATED", "user", user.id, f"username={user.username} role=emp",
          request=request, username=manager.username)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_employee(
    user_id: int,
    data: schemas.UserUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")

    if data.username is not None:
        username = data.username.strip().lower()
        if username != user.username.lower() and db.scalar(
            select(models.User).where(models.User.id != user_id, func.lower(models.User.username) == username)
        ):
            raise HTTPException(409, "Username already exists")
        user.username = username

    if data.full_name is not None:
        user.full_name = data.full_name.strip()

    if data.email is not None:
        email = data.email.strip().lower() or None
        if email and email != (user.email or "").lower() and db.scalar(
            select(models.User).where(models.User.id != user_id, func.lower(models.User.email) == email)
        ):
            raise HTTPException(409, "Email already exists")
        user.email = email

    if data.password is not None:
        user.password_hash = hash_password(data.password)

    audit(db, manager.id, "USER_UPDATED", "user", user.id, f"username={user.username}",
          request=request, username=manager.username)
    db.commit()
    return user


@router.patch("/{user_id}/role", response_model=schemas.UserOut)
def change_role(
    user_id: int,
    data: schemas.UserRoleUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role == "manager":
        raise HTTPException(400, "A manager's role cannot be changed")
    old = user.role
    user.role = data.role
    audit(db, manager.id, "ROLE_CHANGED", "user", user.id, f"{old} -> {data.role}",
          request=request, username=manager.username)
    db.commit()
    return user


@router.patch("/{user_id}/active", response_model=schemas.UserOut)
def set_active(
    user_id: int,
    data: schemas.UserActiveUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    manager: models.User = Depends(manager_only),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == manager.id:
        raise HTTPException(400, "You cannot deactivate yourself")
    user.is_active = data.is_active
    audit(db, manager.id, "USER_ACTIVE_CHANGED", "user", user.id, f"is_active={data.is_active}",
          request=request, username=manager.username)
    db.commit()
    return user
