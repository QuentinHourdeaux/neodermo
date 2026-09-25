"""Static Flask config values that do not come from the environment.

SECRET_KEY and DATABASE_URL are applied in create_app() after .env is
loaded. Reading os.environ at class-definition time would run on import,
before dotenv, and would see empty values.
"""


class Config:
    """Shared defaults for every environment."""

    # Flask-SQLAlchemy signal overhead; not used and always turned off.
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    """Local machine. Secrets still come from .env."""

    DEBUG = True


class TestingConfig(Config):
    """Isolated app for pytest. Never points at the runtime SQLite file."""

    TESTING = True
    DEBUG = False
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
}
