"""Required items the medic marked "unable to obtain" (a patient who cannot give a history, a reading that cannot be
taken). A mark is the medic's statement about the call, not a fact about the patient: it never carries a value, it
never leaves a gap unlisted by guessing, and a later confirmed fact for the same key always wins (AGENTS.md
invariant 6).

A marked key is a vocabulary key, or a checklist item's alternatives joined by "|" (`vitals.gcs_total|
vitals.gcs_motor`), each of them a vocabulary key. Pure functions over the incident: no I/O.
"""
from __future__ import annotations

from typing import Iterable

from .schema import utcnow


class NotObtainedRefused(ValueError):
    """The mark cannot be set: the key already has a confirmed value."""


def alternatives(key: str) -> list[str]:
    return [k.strip() for k in key.split("|") if k.strip()]


def is_markable(key: str, vocabulary) -> bool:
    """A vocabulary key, or "|"-joined alternatives that are all vocabulary keys (never a score or a record item)."""
    parts = alternatives(key)
    return bool(parts) and all(p in vocabulary for p in parts)


def effective(incident, confirmed: dict | None = None) -> list[str]:
    """The marks still in force, in the order made: a key with a confirmed value has dropped out."""
    values = incident.values(confirmed_only=True) if confirmed is None else confirmed
    return [k for k in getattr(incident, "not_obtained", []) if not any(p in values for p in alternatives(k))]


def atomic(marks: Iterable[str]) -> set[str]:
    """Every vocabulary key the marks name."""
    return {p for k in marks for p in alternatives(k)}


def covers(marked: set[str], keys: Iterable[str]) -> bool:
    """Whether any of these keys (or of their "|" alternatives) is marked."""
    return any(p in marked for k in keys for p in alternatives(k))


def mark(incident, key: str, on: bool, actor: str = "medic") -> bool:
    """Set or clear one mark; True when it changed. Refuses on an ended incident (IncidentEnded) and refuses to mark
    a key that already has a confirmed value (NotObtainedRefused). Every change is audit-logged."""
    with incident.lock:
        incident.ensure_open()
        if on and any(p in incident.values(confirmed_only=True) for p in alternatives(key)):
            raise NotObtainedRefused(f"{key} already has a confirmed value")
        present = key in incident.not_obtained
        if on == present:
            return False
        if on:
            incident.not_obtained.append(key)
        else:
            incident.not_obtained.remove(key)
        incident.audit_log.append({"at": utcnow().isoformat(), "action": "not_obtained", "actor": actor,
                                   "key": key, "on": on})
        return True
