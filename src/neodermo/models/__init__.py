"""Import the domain models so Alembic sees their tables."""

from neodermo.models.assessment import Assessment, AssessmentFinding
from neodermo.models.establishment import Establishment
from neodermo.models.patient import Patient
from neodermo.models.stay import PatientStay
from neodermo.models.wound import Wound

__all__ = ["Assessment", "AssessmentFinding", "Establishment", "Patient", "PatientStay", "Wound"]
