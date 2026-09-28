"""Import the models so Alembic sees all tables."""

from neodermo.models.assessment import Assessment
from neodermo.models.establishment import Establishment
from neodermo.models.patient import Patient
from neodermo.models.stay import PatientStay
from neodermo.models.wound import Wound
from neodermo.models.user import User
from neodermo.models.auth_session import AuthSession
from neodermo.models.password_reset_token import PasswordResetToken

__all__ = [
    "Assessment", "Establishment", "Patient", "PatientStay", "Wound",
    "User", "AuthSession", "PasswordResetToken",
]
