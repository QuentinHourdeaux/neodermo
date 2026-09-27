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


class WoundEdge(StrEnum):
    HOLLOWED = "hollowed"
    MACERATION = "maceration"
    HYPERKERATOSIS = "hyperkeratosis"
    ECZEMA = "eczema"
    EPITHELIALIZATION = "epithelialization"
    NORMAL = "normal"


class WoundTissue(StrEnum):
    LAYER = "layer"
    EPITHELIALIZATION = "epithelialization"
    GRANULATION = "granulation"
    NECROSIS = "necrosis"
    INTACT = "intact"


class PeriwoundSkin(StrEnum):
    REDNESS = "redness"
    WARMTH = "warmth"
    SWELLING = "swelling"
    NORMAL = "normal"
    ECZEMA = "eczema"


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
