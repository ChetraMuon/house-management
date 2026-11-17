"""Create the first manager account:  python -m app.seed"""
from sqlalchemy import func, select

from . import models
from .config import settings
from .database import SessionLocal
from .security import hash_password


def ensure_seed_manager(db):
    username = settings.SEED_MANAGER_USERNAME.strip().lower()
    exists = db.scalar(select(models.User).where(func.lower(models.User.username) == username))
    if exists:
        return False
 
    db.add(models.User(
        username=username,
        password_hash=hash_password(settings.SEED_MANAGER_PASSWORD),
        full_name=settings.SEED_MANAGER_NAME,
        role="manager",
    ))
    db.commit()
    return True


def main():
    with SessionLocal() as db:
        created = ensure_seed_manager(db)
        if created:
            print(f"Manager '{settings.SEED_MANAGER_USERNAME}' created. Change the password after first login!")
        else:
            print(f"User '{settings.SEED_MANAGER_USERNAME}' already exists - nothing to do.")


if __name__ == "__main__":
    main()
