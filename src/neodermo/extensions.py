"""Shared Flask extensions.

Created here, attached to an app in create_app(). That avoids a circular
import: routes and models can import db from this module without importing
the app package.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
