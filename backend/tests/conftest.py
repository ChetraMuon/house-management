import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _disable_real_telegram():
    """Never send real Telegram messages while running the test suite.

    Tests that exercise the Telegram client patch these values back to fake
    credentials inside the test body.
    """
    original_token = settings.TELEGRAM_BOT_TOKEN
    original_chat = settings.TELEGRAM_CHAT_ID
    settings.TELEGRAM_BOT_TOKEN = ""
    settings.TELEGRAM_CHAT_ID = ""
    try:
        yield
    finally:
        settings.TELEGRAM_BOT_TOKEN = original_token
        settings.TELEGRAM_CHAT_ID = original_chat
