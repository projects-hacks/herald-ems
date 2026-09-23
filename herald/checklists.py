"""Alert-ready checklists: what the receiving team needs before a pre-alert.

Deterministic tables. Verify item lists against the county's own
destination/pre-notification policies before the pitch (Santa Clara County EMS).
"@race" means "the RACE stroke scale is complete".
"""
from __future__ import annotations

ALERTS: dict[str, dict] = {
    "stroke": {
        "label": "Stroke alert",
        "items": [
            ("stroke.lkw", "Last known well"),
            ("vitals.glucose", "Glucose"),
            ("@race", "Stroke scale (RACE)"),
            ("meds.anticoagulant", "Anticoagulants"),
            ("stroke.onset_witnessed", "Onset witnessed"),
            ("stroke.deficits", "Deficits described"),
        ],
        "triggers": ["stroke", "weakness", "facial droop", "slurred", "aphasia", "hemipar", "cva", "tia"],
        "unknowns": ["stroke.lkw", "meds.anticoagulant", "stroke.onset_witnessed", "allergies"],
    },
    "stemi": {
        "label": "STEMI alert",
        "items": [
            ("symptom.onset", "Symptom onset"),
            ("ecg.twelve_lead_time", "12-lead time"),
            ("ecg.attached", "12-lead attached"),
            ("allergies", "Allergies"),
            ("meds.anticoagulant", "Anticoagulants"),
            ("vitals.sbp", "Blood pressure"),
        ],
        "triggers": ["chest pain", "stemi", "mi ", "heart attack", "acs", "st elevation"],
        "unknowns": ["symptom.onset", "allergies", "meds.anticoagulant"],
    },
}

DEFAULT_UNKNOWNS = ["allergies", "meds.list"]


def active_alerts(dispatch: str | None, complaint: str | None, has_race: bool) -> list[str]:
    text = f" {(dispatch or '')} {(complaint or '')} ".lower()
    out = [aid for aid, a in ALERTS.items() if any(t in text for t in a["triggers"])]
    if has_race and "stroke" not in out:
        out.append("stroke")
    return out
