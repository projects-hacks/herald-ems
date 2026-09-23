"""Core data model: every input becomes a Fact with provenance.

A Fact is one piece of information about the patient ("vitals.sbp = 148"),
tagged with who it came from, how it was captured, and how confident we are.
Facts are append-only; the current picture is a projection over them (state.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

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


class Fact(FactIn):
    id: str
    ts: datetime
    status: Status
    previous_value: Any = None
    previous_ts: Optional[datetime] = None


# Canonical keys. Extractors must only emit these. `kind` drives the UI:
#   measure  = captured by examining/measuring (goes to "missing" when absent)
#   history  = must be asked (goes to "unknown / not yet asked" when absent)
# "range" is a physical-plausibility bound, not a clinical threshold: it rejects values that cannot be real
# ("sats 400", an unconverted 101.8 read as Celsius), whichever extractor produced them (safety validator,
# applied in Incident.validate for every source). Photo readings also have tighter bounds (vision.RANGES).
KEYS: dict[str, dict] = {
    "patient.age":            {"label": "Age", "type": "int", "kind": "history", "range": (0, 120)},
    "patient.sex":            {"label": "Sex", "type": "str", "kind": "history"},
    "complaint.chief":        {"label": "Chief complaint", "type": "str", "kind": "history"},
    "symptom.onset":          {"label": "Symptom onset", "type": "time", "kind": "history"},
    "stroke.lkw":             {"label": "Last known well", "type": "time", "kind": "history"},
    "stroke.onset_witnessed": {"label": "Onset witnessed", "type": "bool", "kind": "history"},
    "stroke.deficits":        {"label": "Deficits", "type": "list", "kind": "measure", "merge": "accumulate"},
    "exam.race.facial":       {"label": "RACE facial palsy (0-2)", "type": "int", "kind": "measure", "range": (0, 2)},
    "exam.race.arm":          {"label": "RACE arm motor (0-2)", "type": "int", "kind": "measure", "range": (0, 2)},
    "exam.race.leg":          {"label": "RACE leg motor (0-2)", "type": "int", "kind": "measure", "range": (0, 2)},
    "exam.race.gaze":         {"label": "RACE head/gaze deviation (0-1)", "type": "int", "kind": "measure", "range": (0, 1)},
    "exam.race.aphasia_agnosia": {"label": "RACE aphasia/agnosia (0-2)", "type": "int", "kind": "measure", "range": (0, 2)},
    "exam.gfast.gaze":        {"label": "G.F.A.S.T. gaze abnormalities (0-1)", "type": "int", "kind": "measure", "range": (0, 1)},
    "exam.gfast.facial":      {"label": "G.F.A.S.T. facial asymmetry (0-1)", "type": "int", "kind": "measure", "range": (0, 1)},
    "exam.gfast.arm_leg":     {"label": "G.F.A.S.T. arm or leg weakness/drift (0-1)", "type": "int", "kind": "measure", "range": (0, 1)},
    "exam.gfast.speech":      {"label": "G.F.A.S.T. speech difficulties (0-1)", "type": "int", "kind": "measure", "range": (0, 1)},
    "vitals.sbp":             {"label": "Systolic BP", "type": "int", "unit": "mmHg", "kind": "measure", "range": (0, 300)},
    "vitals.dbp":             {"label": "Diastolic BP", "type": "int", "unit": "mmHg", "kind": "measure", "range": (0, 200)},
    "vitals.hr":              {"label": "Heart rate", "type": "int", "unit": "/min", "kind": "measure", "range": (0, 300)},
    "vitals.rr":              {"label": "Respiratory rate", "type": "int", "unit": "/min", "kind": "measure", "range": (0, 80)},
    "vitals.spo2":            {"label": "SpO2", "type": "int", "unit": "%", "kind": "measure", "range": (0, 100)},
    "vitals.temp":            {"label": "Temperature", "type": "float", "unit": "°C", "kind": "measure", "range": (25, 45)},
    "vitals.glucose":         {"label": "Glucose", "type": "int", "unit": "mg/dL", "kind": "measure", "range": (1, 2000)},
    "vitals.on_oxygen":       {"label": "Supplemental oxygen", "type": "bool", "kind": "measure"},
    "vitals.consciousness":   {"label": "Consciousness (ACVPU)", "type": "str", "kind": "measure"},
    "vitals.gcs_motor":       {"label": "GCS motor", "type": "int", "kind": "measure", "range": (1, 6)},
    "meds.list":              {"label": "Medications", "type": "list", "kind": "history", "merge": "accumulate"},
    "meds.anticoagulant":     {"label": "Anticoagulant", "type": "str", "kind": "history"},
    "allergies":              {"label": "Allergies", "type": "list", "kind": "history"},
    "code_status":            {"label": "Code status (POLST/DNR)", "type": "str", "kind": "history", "require_tap": True},
    "ecg.twelve_lead_time":   {"label": "12-lead time", "type": "time", "kind": "measure"},
    "ecg.attached":           {"label": "12-lead attached", "type": "bool", "kind": "measure"},
    "transport.destination":  {"label": "Destination", "type": "str", "kind": "history"},
    "transport.eta_min":      {"label": "ETA (min)", "type": "int", "kind": "history", "range": (0, 600)},
    "scene.notes":            {"label": "Scene notes", "type": "list", "kind": "measure", "merge": "accumulate"},
}

# Keys where two different values from different sources are a contradiction,
# not a trend. Vitals change over time; these should not.
CONTRADICTION_KEYS = {
    "allergies", "meds.anticoagulant", "code_status", "stroke.lkw",
    "patient.age", "patient.sex", "stroke.onset_witnessed",
}
