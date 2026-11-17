from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./house_management.db"
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173"
    APPROVAL_THRESHOLD: Decimal = Decimal("10000.00")
    PRODUCT_IMAGE_DIR: str = "uploads/products"
    # Sign-in and audit rows older than this many days are removed automatically.
    LOG_RETENTION_DAYS: int = 7

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ABA PayWay (QR / ABA Pay). Leave PAYWAY_ENABLED=false to keep manual
    # card/transfer recording only.
    PAYWAY_ENABLED: bool = False
    PAYWAY_MERCHANT_ID: str = ""
    PAYWAY_API_KEY: str = ""
    PAYWAY_BASE_URL: str = "https://checkout-sandbox.payway.com.kh"
    # Public HTTPS URL of POST /api/payments/payway/webhook. Optional: the
    # checkout screen also polls the status API, so local dev works without it.
    PAYWAY_CALLBACK_URL: str = ""
    PAYWAY_QR_LIFETIME_MINUTES: int = 10
    PAYWAY_QR_IMAGE_TEMPLATE: str = "template3_color"
    PAYWAY_CURRENCY: str = "USD"
    # Sandbox-only helper that marks a pending test QR as paid without moving
    # real money. Never available when the production PayWay URL is configured.
    PAYWAY_SIMULATOR_ENABLED: bool = False

    SEED_MANAGER_USERNAME: str = "manager"
    SEED_MANAGER_PASSWORD: str = "ChangeMe123!"
    SEED_MANAGER_NAME: str = "Store Manager"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
