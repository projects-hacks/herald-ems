"""Capture messages and immutable frame metadata; no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..core.schema import Fact


@dataclass(frozen=True)
class Frame:
    id: str
    ts: float
    jpeg: bytes
    w: int
    h: int
    source: str


@dataclass(frozen=True)
class ROI:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        if not (0 <= self.x0 < self.x1 <= 1 and 0 <= self.y0 < self.y1 <= 1):
            raise ValueError("ROI must be a nonempty normalized rectangle")

    def box(self, w: int, h: int, margin: float = 0):
        dx, dy = (self.x1 - self.x0) * margin, (self.y1 - self.y0) * margin
        return (int(max(0, self.x0 - dx) * w), int(max(0, self.y0 - dy) * h),
                max(1, int(min(1, self.x1 + dx) * w)), max(1, int(min(1, self.y1 + dy) * h)))


@dataclass(frozen=True)
class GateResult:
    sharp: float
    changed: float
    bright: float
    passed: bool
    reason: str
    usable: bool = False


@dataclass(frozen=True)
class IncidentEvent:
    kind: Literal["facts_added", "alert_new", "eta_changed"]
    facts: list[Fact]
    summary_diff: dict = field(default_factory=dict)
    incident_id: str = ""
    states: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CaptureIntent:
    trigger: str
    mode: str
    window_s: float
    roi_target: str | None
    purpose: Literal["record", "verify"] = "record"
    fact_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class CheckResult:
    status: Literal["match", "mismatch", "unreadable"]
    label_drug: str | None = None


@dataclass(frozen=True)
class CaptureResult:
    facts: list[str] = field(default_factory=list)
    photo_id: str | None = None
    reason: str = "read"
