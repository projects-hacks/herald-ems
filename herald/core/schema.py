"""Core data model: every input becomes a Fact with provenance.

A Fact is one piece of information about the patient ("vitals.sbp = 148"),
tagged with who it came from, how it was captured, and how confident we are.
Facts are append-only; the current picture is a projection over them (core/snapshot.py).
The vocabulary of keys is content, in config/vocabulary.yaml (core/vocabulary.py).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class CapturedBy(str, Enum):
    """Who or what put the fact into the system."""
    medic = "medic"      # the medic's push-to-talk mic or a tap
    other = "other"      # someone else speaking into the mic (patient, family, a judge)
    device = "device"    # monitor feed / simulated monitor panel
    camera = "camera"    # read from a photo by the vision model


class Role(str, Enum):
    """Who the information is attributed to ("husband says..." -> family)."""
    medic = "medic"
    patient = "patient"
    family = "family"
    bystander = "bystander"
    device = "device"
    photo = "photo"


def source_role(captured_by: "CapturedBy", speaker: Optional[str] = None, role: Optional[Role] = None) -> Role:
    """Whose information a capture is by default: an explicit role; else a speaker named by a role ("patient",
    "bystander"); else the medic for the medic's own mic, and family for anyone else's."""
    if role is not None:
        return role
    if speaker and speaker.strip().lower() in Role._value2member_map_:
        return Role(speaker.strip().lower())
    return Role.medic if captured_by == CapturedBy.medic else Role.family


class Status(str, Enum):
    unconfirmed = "unconfirmed"
    confirmed = "confirmed"
    rejected = "rejected"


class Provenance(BaseModel):
    audio_id: Optional[str] = None      # data/audio/<audio_id>.wav
    t_start: Optional[float] = None     # seconds into the clip
    t_end: Optional[float] = None
    text: Optional[str] = None          # the transcript span the fact came from
    photo_id: Optional[str] = None      # data/photos/<photo_id>.jpg
    crop: Optional[list[float]] = None  # [x0, y0, x1, y1] normalized
    extractor: Optional[str] = None     # "rules", "llm:<model>", "vision:<model>", "manual"
    hold_reason: Optional[str] = None   # why this fact waits for the medic's tap (shown on screen), e.g. the guard
    normalized: Optional[list[dict]] = None   # drug names: [{said, value, code, method, score}] per item


class FactIn(BaseModel):
    """What an extractor (rules, LLM, vision, manual panel) produces."""
    key: str
    value: Any
    unit: Optional[str] = None
    role: Role = Role.medic
    speaker: Optional[str] = None       # free label: "husband", "daughter", "pulse oximeter"
    captured_by: CapturedBy = CapturedBy.medic
    confidence: float = 0.9
    provenance: Provenance = Field(default_factory=Provenance)
    # RxNorm RxCUI of a drug value; for list keys, one entry per item in order. None (or a None entry) = unresolved.
    code: Optional[Union[str, list[Optional[str]]]] = None


@dataclass(frozen=True)
class NormalizedValue:
    """A drug or allergen name mapped to its standard generic name, or kept as said when nothing matched."""
    value: str                          # ingredient name(s), lowercase; the spoken text when unresolved
    code: Optional[str]                 # RxCUI of the ingredient (or of the multi-ingredient concept)
    score: float                        # 100 for exact; the similarity for fuzzy and phonetic matches
    method: str                         # exact | fuzzy | phonetic | unresolved | ambiguous
    ingredients: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.method in ("exact", "fuzzy", "phonetic")


class Fact(FactIn):
    id: str
    ts: datetime
    status: Status
    previous_value: Any = None
    previous_ts: Optional[datetime] = None
