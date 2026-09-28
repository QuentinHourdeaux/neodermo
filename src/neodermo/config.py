"""Static Flask config values that do not come from the environment.

Runtime overrides are applied in create_app() after .env is loaded. Reading
os.environ at class-definition time would run on import, before dotenv.
"""


class Config:
    """Shared defaults for every environment."""

    # Flask-SQLAlchemy signal overhead; not used and always turned off.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQL errors must not echo token digests or other bound values into logs.
    SQLALCHEMY_ENGINE_OPTIONS = {"hide_parameters": True}
    SESSION_LIFETIME_SECONDS = 43200
    TRUSTED_FRONTEND_ORIGINS = ("http://127.0.0.1:5000",)
    AUTH_COOKIE_SECURE = True


class DevelopmentConfig(Config):
    """Local machine; runtime settings come from .env."""

    DEBUG = True


class TestingConfig(Config):
    """Isolated app for pytest. Never points at the runtime SQLite file."""

    TESTING = True
    DEBUG = False
    TRUSTED_FRONTEND_ORIGINS = ("http://localhost",)
    AUTH_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
}
