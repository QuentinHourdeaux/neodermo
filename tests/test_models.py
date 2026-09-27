"""First domain migration and stored-record invariants."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from flask_migrate import upgrade
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from neodermo import PROJECT_ROOT, create_app
from neodermo.extensions import db
from neodermo.models import (
    Assessment,
    AssessmentFinding,
    Establishment,
    Patient,
    PatientStay,
    Wound,
)
from neodermo.models.enums import Evolution, ExudateLevel, Sex


def _upgrade() -> None:
    upgrade(directory=str(PROJECT_ROOT / "migrations"))


@pytest.fixture
def migrated_app():
    """Run the real migration against a fresh, isolated in-memory database."""
    app = create_app("testing")
    with app.app_context():
        _upgrade()
        yield app


def _patient(establishment: Establishment, room: str = "12", bed: str | None = None) -> Patient:
    patient = Patient(name="Fictional Patient")
    patient.stays.append(
        PatientStay(
            establishment=establishment,
            room=room,
            bed=bed,
            start_date=date(2026, 9, 1),
        )
    )
    return patient


def test_upgrade_preserves_existing_tables_and_is_repeatable():
    app = create_app("testing")
    with app.app_context():
        db.session.execute(text("CREATE TABLE legacy_marker (value TEXT NOT NULL)"))
        db.session.execute(text("INSERT INTO legacy_marker VALUES ('keep')"))
        db.session.commit()

        _upgrade()
        names = set(inspect(db.engine).get_table_names())
        _upgrade()

        assert names == set(inspect(db.engine).get_table_names())
        assert names == {
            "alembic_version",
            "legacy_marker",
            "establishments",
            "patients",
            "patient_stays",
            "wounds",
            "assessments",
            "assessment_findings",
        }
        assert db.session.scalar(text("SELECT value FROM legacy_marker")) == "keep"
        assert db.session.scalar(text("PRAGMA foreign_keys")) == 1


def test_patient_two_wounds_and_assessments_round_trip(migrated_app):
    establishment = Establishment(
        name=" Fictional Clinic ",
        address="Demo Street 1",
        phone_number="000000000",
        email="demo@example.invalid",
        notes="Fictional establishment",
    )
    patient = _patient(establishment, bed="  A ")
    patient.birth_date = date(1950, 4, 3)
    first_wound = Wound(patient=patient, placement="Left heel")
    second_wound = Wound(patient=patient)
    observed = datetime(2026, 9, 26, 14, 30, tzinfo=timezone(timedelta(hours=2)))
    first = Assessment(
        wound=first_wound,
        observed_at=observed,
        exudate_level=ExudateLevel.MOIST,
        evolution=Evolution.IMPROVED,
        infection=False,
        length_cm=Decimal("1.50"),
        width_cm=Decimal("0.75"),
        depth_cm=Decimal("0.00"),
        remarks="Fictional example",
    )
    first.findings.extend(
        [
            AssessmentFinding(category="periwound_skin", value="redness"),
            AssessmentFinding(category="periwound_skin", value="warmth"),
            AssessmentFinding(category="wound_edges", value="hollowed"),
            AssessmentFinding(category="wound_tissue", value="layer"),
        ]
    )
    second = Assessment(wound=second_wound, observed_at=datetime(2026, 9, 25, tzinfo=UTC))
    db.session.add_all([patient, first, second])
    db.session.commit()
    patient_id, first_id, second_id = patient.id, first.id, second.id
    db.session.expire_all()

    saved_patient = db.session.get(Patient, patient_id)
    saved_first = db.session.get(Assessment, first_id)
    saved_second = db.session.get(Assessment, second_id)

    assert saved_patient.reference.startswith("ND-")
    assert saved_patient.name == "Fictional Patient"
    assert saved_patient.stays[0].establishment.name == "Fictional Clinic"
    assert saved_patient.stays[0].establishment.email == "demo@example.invalid"
    assert saved_patient.stays[0].bed == "A"
    assert saved_patient.birth_date == date(1950, 4, 3)
    assert saved_patient.sex is None
    assert saved_patient.allergies == ""
    assert saved_patient.archived_at is None
    assert len(saved_patient.wounds) == 2
    assert saved_first.wound_id != saved_second.wound_id
    assert saved_first.observed_at == datetime(2026, 9, 26, 12, 30, tzinfo=UTC)
    assert saved_first.observed_at.tzinfo is UTC
    assert saved_first.length_cm == Decimal("1.50")
    assert saved_first.width_cm == Decimal("0.75")
    assert saved_first.infection is False
    assert {(item.category, item.value) for item in saved_first.findings} == {
        ("periwound_skin", "redness"),
        ("periwound_skin", "warmth"),
        ("wound_edges", "hollowed"),
        ("wound_tissue", "layer"),
    }
    assert saved_second.infection is None
    assert saved_second.evolution is None
    assert saved_second.length_cm is None
    assert saved_second.observations is None
    assert saved_second.remarks is None
    assert saved_first.created_at.tzinfo is UTC


def test_allergy_text_and_sex_round_trip(migrated_app):
    patient = Patient(
        name=" Fictional Patient ",
        sex=Sex.FEMALE,
        allergies=" Fictional pollen allergy ",
    )
    patient.stays.append(
        PatientStay(
            establishment=Establishment(name="Fictional Clinic"),
            start_date=date(2026, 9, 1),
        )
    )
    db.session.add(patient)
    db.session.commit()
    patient_id = patient.id
    db.session.expire_all()

    saved = db.session.get(Patient, patient_id)
    assert saved.name == "Fictional Patient"
    assert saved.sex is Sex.FEMALE
    assert saved.allergies == "Fictional pollen allergy"


def test_patient_name_is_required(migrated_app):
    db.session.add(Patient())
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_stay_move_and_transfer_preserve_patient_and_wound_history(migrated_app):
    source = Establishment(name="Source Clinic")
    destination = Establishment(name="Destination Clinic")
    patient = _patient(source)
    wound = Wound(patient=patient)
    assessment = Assessment(wound=wound, observed_at=datetime.now(UTC))
    db.session.add_all([patient, destination, assessment])
    db.session.commit()
    patient_id, reference, patient_updated_at, wound_id, assessment_id = (
        patient.id,
        patient.reference,
        patient.updated_at,
        wound.id,
        assessment.id,
    )
    original_stay = patient.stays[0]
    original_stay_id = original_stay.id

    original_stay.room = "14"
    original_stay.bed = "B"
    original_stay.service = "Fictional ward"
    db.session.commit()
    assert patient.updated_at == patient_updated_at
    assert patient.stays[0].id == original_stay_id

    original_stay.end_date = date(2026, 9, 10)
    new_stay = PatientStay(
        patient=patient,
        establishment=destination,
        start_date=date(2026, 9, 11),
        room="21",
    )
    db.session.add(new_stay)
    db.session.commit()
    db.session.expire_all()

    saved = db.session.get(Patient, patient_id)
    assert saved.reference == reference
    assert saved.updated_at == patient_updated_at
    assert len(saved.stays) == 2
    assert db.session.get(PatientStay, original_stay_id).room == "14"
    assert db.session.get(PatientStay, original_stay_id).end_date == date(2026, 9, 10)
    assert new_stay.establishment.name == "Destination Clinic"
    assert new_stay.end_date is None
    assert db.session.get(Wound, wound_id).patient_id == patient_id
    assert db.session.get(Assessment, assessment_id).wound_id == wound_id


def test_reopening_wound_preserves_history_and_allows_new_assessments(migrated_app):
    wound = Wound(patient=_patient(Establishment(name="Fictional Clinic")))
    first = Assessment(wound=wound, observed_at=datetime(2026, 9, 25, tzinfo=UTC))
    db.session.add(first)
    db.session.commit()

    assert wound.closed_at is None
    closed_at = datetime(2026, 9, 25, 18, tzinfo=UTC)
    wound.closed_at = closed_at
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Wound, wound.id).closed_at == closed_at

    wound.closed_at = None
    second = Assessment(wound=wound, observed_at=datetime(2026, 9, 26, tzinfo=UTC))
    db.session.add(second)
    db.session.commit()
    wound_id = wound.id
    db.session.expire_all()

    saved = db.session.get(Wound, wound_id)
    assert saved.closed_at is None
    assert {entry.id for entry in saved.assessments} == {first.id, second.id}


def test_patient_has_at_most_one_ongoing_stay(migrated_app):
    source = Establishment(name="Source Clinic")
    destination = Establishment(name="Destination Clinic")
    patient = _patient(source)
    db.session.add_all([patient, destination])
    db.session.commit()

    db.session.add(
        PatientStay(
            patient=patient,
            establishment=destination,
            start_date=date(2026, 9, 2),
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    patient.stays[0].end_date = date(2026, 9, 3)
    db.session.add(
        PatientStay(
            patient=patient,
            establishment=destination,
            start_date=date(2026, 9, 4),
        )
    )
    db.session.commit()
    assert len(db.session.scalars(select(PatientStay)).all()) == 2


def test_stays_may_share_establishment_room_and_bed(migrated_app):
    establishment = Establishment(name="Fictional Clinic")
    patients = [_patient(establishment, bed="A") for _ in range(50)]
    patients.extend(
        [_patient(establishment, room="13", bed="  "), _patient(establishment, room="13")]
    )
    db.session.add_all(patients)
    db.session.commit()

    saved_patients = db.session.scalars(select(Patient)).all()
    saved_stays = db.session.scalars(select(PatientStay)).all()
    assert len(saved_patients) == len(saved_stays) == 52
    assert len({patient.id for patient in saved_patients}) == 52
    assert len({patient.reference for patient in saved_patients}) == 52
    assert sum(stay.bed == "A" and stay.room == "12" for stay in saved_stays) == 50
    assert sum(stay.bed is None and stay.room == "13" for stay in saved_stays) == 2


def test_foreign_keys_enums_numbers_and_findings_are_checked(migrated_app):
    establishment = Establishment(name="Fictional Clinic")
    patient = _patient(establishment)
    wound = Wound(patient=patient)
    assessment = Assessment(wound=wound, observed_at=datetime.now(UTC))
    db.session.add(assessment)
    db.session.commit()

    invalid_statements = [
        ("UPDATE patients SET name = NULL WHERE id = :id", patient.id),
        ("UPDATE patients SET name = '   ' WHERE id = :id", patient.id),
        ("UPDATE patients SET name = ' Untrimmed ' WHERE id = :id", patient.id),
        ("UPDATE patients SET sex = 'invalid' WHERE id = :id", patient.id),
        ("UPDATE patients SET allergies = NULL WHERE id = :id", patient.id),
        (
            "UPDATE patient_stays SET end_date = '2026-08-31' WHERE id = :id",
            patient.stays[0].id,
        ),
        ("UPDATE assessments SET evolution = 'invalid' WHERE id = :id", assessment.id),
        ("UPDATE assessments SET exudate_level = 'invalid' WHERE id = :id", assessment.id),
        ("UPDATE assessments SET wound_color = 'invalid' WHERE id = :id", assessment.id),
        ("UPDATE assessments SET odor = 'invalid' WHERE id = :id", assessment.id),
        ("UPDATE assessments SET length_cm = -0.5 WHERE id = :id", assessment.id),
        ("UPDATE assessments SET length_cm = 'not a number' WHERE id = :id", assessment.id),
        ("UPDATE assessments SET infection = 2 WHERE id = :id", assessment.id),
        (
            "INSERT INTO assessment_findings (assessment_id, category, value) "
            "VALUES (:id, 'wound_tissue', 'warmth')",
            assessment.id,
        ),
    ]
    for statement, record_id in invalid_statements:
        with pytest.raises(IntegrityError):
            db.session.execute(text(statement), {"id": record_id})
            db.session.commit()
        db.session.rollback()

    db.session.add(Wound(patient_id="missing"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    db.session.add(
        PatientStay(
            patient_id="missing",
            establishment_id=establishment.id,
            start_date=date(2026, 9, 1),
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    db.session.add(
        AssessmentFinding(assessment_id="missing", category="wound_edges", value="normal")
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    db.session.add(
        AssessmentFinding(assessment=assessment, category="wound_edges", value="normal")
    )
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(
            text(
                "INSERT INTO assessment_findings (assessment_id, category, value) "
                "VALUES (:id, 'wound_edges', 'normal')"
            ),
            {"id": assessment.id},
        )
        db.session.commit()
    db.session.rollback()


def test_failed_transaction_leaves_no_partial_records(migrated_app):
    establishment = Establishment(name="Fictional Clinic")
    db.session.add(establishment)
    db.session.commit()

    patient = _patient(establishment)
    db.session.add_all([patient, Wound(patient_id="missing")])
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    assert db.session.scalar(select(Patient)) is None


def test_observation_time_must_be_aware(migrated_app):
    establishment = Establishment(name="Fictional Clinic")
    wound = Wound(patient=_patient(establishment))
    db.session.add(Assessment(wound=wound, observed_at=datetime(2026, 9, 26, 12, 30)))

    with pytest.raises(StatementError):
        db.session.commit()
    db.session.rollback()
