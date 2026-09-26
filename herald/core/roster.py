"""Patient roster for a multi-patient incident; domain state only, with no I/O."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .incident import Incident


class PatientRoster:
    """Own separate patient incidents and identify which one capture routes target."""

    def __init__(self, incident_factory: Callable[[], Incident]):
        self._factory = incident_factory
        self._incidents: dict[str, Incident] = {}
        self._labels: dict[str, str] = {}
        self.active_id: str | None = None

    def add(self, label: str) -> Incident:
        label = label.strip()
        if not label:
            raise ValueError("patient label must not be empty")
        incident = self._factory()
        incident.patient_label = label
        self._incidents[incident.id] = incident
        self._labels[incident.id] = label
        self.active_id = incident.id
        return incident

    def activate(self, patient_id: str) -> Incident:
        try:
            incident = self._incidents[patient_id]
        except KeyError:
            raise KeyError(patient_id) from None
        self.active_id = patient_id
        return incident

    def active(self) -> Incident:
        if self.active_id is None:
            raise RuntimeError("patient roster is empty")
        return self._incidents[self.active_id]

    def incidents(self) -> list[Incident]:
        return list(self._incidents.values())

    def summaries(self) -> list[dict[str, Any]]:
        rows = []
        for patient_id, incident in self._incidents.items():
            snapshot = incident.snapshot()
            triage = incident.latest("triage.category", confirmed_only=True)
            readiness = snapshot["readiness"][0] if snapshot["readiness"] else None
            rows.append({
                "id": patient_id,
                "label": getattr(incident, "display_label", None) or self._labels[patient_id],   # confirmed name, else slot
                "slot": self._labels[patient_id],
                "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
                "triage": triage.value if triage else None,
                "summary": snapshot["summary"],
                "readiness_done": readiness["done"] if readiness else 0,
                "readiness_total": readiness["total"] if readiness else 0,
            })
        return rows
