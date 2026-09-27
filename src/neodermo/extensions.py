"""Shared Flask extensions.

Created here, attached to an app in create_app(). That avoids a circular
import: routes and models can import db from this module without importing
the app package.
"""

import sqlite3

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(connection, connection_record) -> None:
    """Enforce foreign keys on every SQLite connection, including tests."""
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")
