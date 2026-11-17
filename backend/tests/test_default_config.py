from app.config import Settings


def test_default_database_is_sqlite_for_local_dev():
    settings = Settings(_env_file=None)
    assert settings.DATABASE_URL.startswith("sqlite")
