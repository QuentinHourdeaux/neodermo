"""Stored choices for the initial wound-care schema."""

from enum import StrEnum

from sqlalchemy import Enum


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class Evolution(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    WORSENED = "worsened"


class ExudateLevel(StrEnum):
    DRY = "dry"
    MOIST = "moist"
    WET = "wet"


class WoundColor(StrEnum):
    RED = "red"
    BLACK = "black"
    YELLOW = "yellow"


class Odor(StrEnum):
    NONE = "none"
    MILD = "mild"
    STRONG = "strong"


class FindingCategory(StrEnum):
    WOUND_EDGES = "wound_edges"
    WOUND_TISSUE = "wound_tissue"
    PERIWOUND_SKIN = "periwound_skin"


class FindingValue(StrEnum):
    HOLLOWED = "hollowed"
    MACERATION = "maceration"
    HYPERKERATOSIS = "hyperkeratosis"
    ECZEMA = "eczema"
    EPITHELIALIZATION = "epithelialization"
    NORMAL = "normal"
    LAYER = "layer"
    GRANULATION = "granulation"
    NECROSIS = "necrosis"
    INTACT = "intact"
    REDNESS = "redness"
    WARMTH = "warmth"
    SWELLING = "swelling"


def stored_enum(enum_class: type[StrEnum], name: str) -> Enum:
    """Persist enum values and emit a database CHECK constraint."""
    return Enum(
        enum_class,
        values_callable=lambda values: [member.value for member in values],
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=name,
    )
