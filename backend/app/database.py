from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=not settings.DATABASE_URL.startswith("sqlite"),
    pool_recycle=3600,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _migrate_schema() -> None:
    from . import models  # noqa: F401

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "sales" in tables:
            sales_columns = {column["name"] for column in inspector.get_columns("sales")}
            if "customer_id" not in sales_columns:
                conn.execute(text("ALTER TABLE sales ADD COLUMN customer_id INTEGER NULL"))
            if "customer_name" not in sales_columns:
                conn.execute(text("ALTER TABLE sales ADD COLUMN customer_name VARCHAR(120) NULL"))

        if "products" in tables:
            product_columns = {column["name"] for column in inspector.get_columns("products")}
            if "image_url" not in product_columns:
                conn.execute(text("ALTER TABLE products ADD COLUMN image_url VARCHAR(255) NULL"))

        if "payments" in tables:
            payment_columns = {column["name"] for column in inspector.get_columns("payments")}
            additions = {
                "provider": "VARCHAR(30) NULL",
                "provider_txn_id": "VARCHAR(40) NULL",
                "provider_ref": "VARCHAR(60) NULL",
                "provider_qr": "TEXT NULL",
                "status": "VARCHAR(20) NOT NULL DEFAULT 'SUCCEEDED'",
                "stock_reserved": "BOOLEAN NOT NULL DEFAULT 0",
                "expires_at": "DATETIME NULL",
                "raw_response": "TEXT NULL",
            }
            for name, ddl in additions.items():
                if name not in payment_columns:
                    conn.execute(text(f"ALTER TABLE payments ADD COLUMN {name} {ddl}"))

        if "audit_logs" in tables:
            audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
            if "username" not in audit_columns:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN username VARCHAR(50) NULL"))
            if "ip_address" not in audit_columns:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN ip_address VARCHAR(45) NULL"))
            if "users" in tables:
                # Backfill the username for entries written before this column existed.
                conn.execute(text(
                    "UPDATE audit_logs SET username = "
                    "(SELECT users.username FROM users WHERE users.id = audit_logs.actor_id) "
                    "WHERE username IS NULL AND actor_id IS NOT NULL"
                ))

    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    with SessionLocal() as db:
        legacy_sales = db.scalars(
            select(models.Sale).where(models.Sale.customer_id.is_(None), models.Sale.customer_name.is_not(None))
        ).all()
        for sale in legacy_sales:
            name = (sale.customer_name or "").strip()
            if not name:
                continue
            customer = db.scalar(select(models.Customer).where(models.Customer.full_name == name))
            if customer is None:
                customer = models.Customer(phone=f"legacy-{sale.id:06d}", full_name=name)
                db.add(customer)
                db.flush()
            sale.customer_id = customer.id
        db.commit()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_sqlite_schema() -> None:
    """Backwards-compatible alias (older tests and scripts call this name)."""
    _migrate_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
