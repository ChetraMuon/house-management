from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import audit, client_info, get_current_user
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(data: schemas.LoginIn, request: Request, db: Session = Depends(get_db)):
    ip, ua = client_info(request)
    username = data.username.strip().lower()
    user = db.scalar(select(models.User).where(func.lower(models.User.username) == username))

    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        db.add(models.LoginLog(
            user_id=user.id if user else None, username=username[:50],
            event="LOGIN_FAILED", ip_address=ip, user_agent=ua,
        ))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    db.add(models.LoginLog(user_id=user.id, username=user.username, event="LOGIN", ip_address=ip, user_agent=ua))
    db.commit()
    return schemas.TokenOut(access_token=create_access_token(user.id, user.role), user=user)


@router.post("/logout", status_code=204)
def logout(request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    ip, ua = client_info(request)
    db.add(models.LoginLog(user_id=user.id, username=user.username, event="LOGOUT", ip_address=ip, user_agent=ua))
    db.commit()


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
def change_password(
    data: schemas.PasswordChange,
    request: Request,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "Old password is incorrect")
    user.password_hash = hash_password(data.new_password)
    audit(db, user.id, "PASSWORD_CHANGED", "user", user.id,
          request=request, username=user.username)
    db.commit()
