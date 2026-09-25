"""FHIR R4 Bundle of the confirmed record (GET /api/handoff/fhir): what a receiving system could ingest.

Every entry comes from a confirmed fact, or a score computed from confirmed facts only (AGENTS.md invariant 4,
`herald/core/snapshot.py` already computes `snapshot()["scores"]` from `values(confirmed_only=True)`). Nothing
waiting for the medic's tap ever appears here -- exactly the same guarantee the relay and the handoff report already
give, just shaped as standard resources instead of a critical packet or a read-aloud line. This module decides no
clinical content of its own: codes live in config/fhir_codes.yaml (vitals/scores) and are reused from
herald/terminology/ (drugs/allergies) wherever a fact already carries one; where none is available a resource still
appears, with `text` only, never a fabricated code.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..config import load_yaml
from ..core.schema import Coding
from ..core.vocabulary import Vocabulary, norm_value
from ..scoring import ScaleRegistry

OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
COND_VER_STATUS = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
ALLERGY_CLINICAL = "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical"

_GENDER = {"m": "male", "male": "male", "f": "female", "female": "female",
          "other": "other", "unknown": "unknown"}
_ID_SAFE = re.compile(r"[^A-Za-z0-9.-]+")


def _slug(text: Any, limit: int = 40) -> str:
    """A FHIR-id-safe token ([A-Za-z0-9.-]{1,64}) from arbitrary fact content, never empty."""
    s = _ID_SAFE.sub("-", str(text)).strip("-").lower()
    return (s or "x")[:limit]


def _coding(code: Optional[Coding], display: Optional[str] = None) -> Optional[dict]:
    if not isinstance(code, Coding):
        return None
    out = {"system": code.system, "code": code.code}
    if display:
        out["display"] = display
    return out


def _quantity(value: Any, unit_text: Optional[str], ucum: Optional[str], ucum_system: str) -> Optional[dict]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out: dict[str, Any] = {"value": value}
    if unit_text:
        out["unit"] = unit_text
    if ucum:
        out.update(system=ucum_system, code=ucum)
    return out


class FhirExport:
    def __init__(self, codes: dict, vocabulary: Vocabulary, scales: ScaleRegistry):
        self.codes, self.vocab, self.scales = codes, vocabulary, scales

    @classmethod
    def from_config(cls, vocabulary: Vocabulary, scales: ScaleRegistry, rel: str = "fhir_codes.yaml") -> "FhirExport":
        return cls(load_yaml(rel), vocabulary, scales)

    def problems(self) -> list[str]:
        """Content checks: a typo here should fail loudly at startup, not silently drop a vital from every export."""
        out = []
        for key in self.codes.get("vitals", {}):
            if key not in self.vocab.keys:
                out.append(f"fhir_codes.yaml: vitals key {key} is not in the vocabulary")
        for key in ("patient.name", "patient.identifier", "patient.sex", "patient.age", "impression.primary",
                   "trauma.injuries", "allergies", "meds.given"):
            if key not in self.vocab.keys:
                out.append(f"fhir_codes.yaml: expected vocabulary key {key} is missing")
        return out

    # ---------- the bundle ----------
    def build(self, incident, patient_id: Optional[str] = None) -> dict:
        with incident.lock:
            pid = patient_id or f"patient-{incident.id}"
            resources = [self._patient(incident, pid)]
            resources += self._vitals(incident, pid)
            resources += self._age(incident, pid)
            resources += self._scores(incident, pid)
            resources += self._medications(incident, pid)
            resources += self._allergies(incident, pid)
            resources += self._conditions(incident, pid)
            return {"resourceType": "Bundle", "type": "collection", "timestamp": incident.started.isoformat(),
                   "entry": [{"resource": r} for r in resources]}

    # ---------- resources ----------
    def _patient(self, incident, pid: str) -> dict:
        vals = incident.values(confirmed_only=True)
        r: dict[str, Any] = {"resourceType": "Patient", "id": pid}
        if "patient.identifier" in vals:
            r["identifier"] = [{"value": str(vals["patient.identifier"])}]
        if "patient.name" in vals:
            r["name"] = [{"text": str(vals["patient.name"])}]
        if "patient.sex" in vals:
            r["gender"] = _GENDER.get(str(vals["patient.sex"]).strip().lower(), "unknown")
        return r

    def _vitals(self, incident, pid: str) -> list[dict]:
        loinc, ucum_system = self.codes["system"]["loinc"], self.codes["system"]["ucum"]
        out = []
        for key, spec in self.codes.get("vitals", {}).items():
            for f in incident.history(key, confirmed_only=True):
                qty = _quantity(f.value, f.unit or self.vocab.meta(key).get("unit"), spec.get("ucum"), ucum_system)
                if qty is None:
                    continue
                out.append({
                    "resourceType": "Observation", "id": f"obs-{f.id}", "status": "final",
                    "category": [{"coding": [{"system": OBS_CATEGORY, "code": "vital-signs"}]}],
                    "code": {"coding": [{"system": loinc, "code": spec["loinc"], "display": spec["display"]}]},
                    "subject": {"reference": f"Patient/{pid}"},
                    "effectiveDateTime": f.ts.isoformat(),
                    "valueQuantity": qty,
                })
        return out

    def _age(self, incident, pid: str) -> list[dict]:
        spec = self.codes.get("age")
        if not spec:
            return []
        loinc, ucum_system = self.codes["system"]["loinc"], self.codes["system"]["ucum"]
        out = []
        for f in incident.history("patient.age", confirmed_only=True):
            qty = _quantity(f.value, "years", spec.get("ucum"), ucum_system)
            if qty is None:
                continue
            out.append({
                "resourceType": "Observation", "id": f"obs-{f.id}", "status": "final",
                "category": [{"coding": [{"system": OBS_CATEGORY, "code": "social-history"}]}],
                "code": {"coding": [{"system": loinc, "code": spec["loinc"], "display": spec["display"]}]},
                "subject": {"reference": f"Patient/{pid}"},
                "effectiveDateTime": f.ts.isoformat(),
                "valueQuantity": qty,
            })
        return out

    def _scores(self, incident, pid: str) -> list[dict]:
        """The county-active scores, from the SAME confirmed-only evaluation the snapshot already computed
        (herald/core/snapshot.py Projector.snapshot), read here straight from the incident so this export needs
        no snapshot/Projector wiring of its own."""
        snap = incident.snapshot()
        scores_system = self.codes["system"]["scores"]
        out = []
        for sid, result in snap["scores"].items():
            if sid not in self.scales:
                continue
            text = self.scales[sid].relay_text(result)
            if text is None:
                continue
            out.append({
                "resourceType": "Observation", "id": f"obs-score-{sid}-{incident.id}", "status": "final",
                "category": [{"coding": [{"system": OBS_CATEGORY, "code": "survey"}]}],
                "code": {"coding": [{"system": scores_system, "code": sid,
                                    "display": result.get("name", sid)}]},
                "subject": {"reference": f"Patient/{pid}"},
                "effectiveDateTime": incident.facts[-1].ts.isoformat() if incident.facts else incident.started.isoformat(),
                "valueString": text,
            })
        return out

    def _medications(self, incident, pid: str) -> list[dict]:
        out, seen = [], set()
        for f in incident.history("meds.given", confirmed_only=True):
            key = norm_value(f.value)
            if key in seen:
                continue
            seen.add(key)
            record = f.value if isinstance(f.value, dict) else {}
            drug = record.get("drug")
            concept: dict[str, Any] = {"text": str(drug) if drug else "unknown medication"}
            coding = _coding(f.code if isinstance(f.code, Coding) else None, concept["text"])
            if coding:
                concept["coding"] = [coding]
            r: dict[str, Any] = {
                "resourceType": "MedicationAdministration", "id": f"medadmin-{f.id}", "status": "completed",
                "medicationCodeableConcept": concept,
                "subject": {"reference": f"Patient/{pid}"},
                "effectiveDateTime": f.ts.isoformat(),
            }
            dose, unit, route, by = record.get("dose"), record.get("unit"), record.get("route"), record.get("by")
            if isinstance(dose, (int, float)) and not isinstance(dose, bool):
                r["dosage"] = {"dose": {"value": dose, **({"unit": unit} if unit else {})}}
                if route:
                    r["dosage"]["route"] = {"text": str(route)}
            if by:
                r["note"] = [{"text": f"given by {by}"}]
            out.append(r)
        return out

    def _allergies(self, incident, pid: str) -> list[dict]:
        latest = incident.latest("allergies", confirmed_only=True)
        if not latest or not isinstance(latest.value, list):
            return []
        codes = latest.code if isinstance(latest.code, list) else [None] * len(latest.value)
        out = []
        for item, code in zip(latest.value, codes):
            concept: dict[str, Any] = {"text": str(item)}
            coding = _coding(code if isinstance(code, Coding) else None, str(item))
            if coding:
                concept["coding"] = [coding]
            out.append({
                "resourceType": "AllergyIntolerance", "id": f"allergy-{latest.id}-{_slug(item)}",
                "clinicalStatus": {"coding": [{"system": ALLERGY_CLINICAL, "code": "active"}]},
                "code": concept,
                "patient": {"reference": f"Patient/{pid}"},
                "recordedDate": latest.ts.isoformat(),
            })
        return out

    def _conditions(self, incident, pid: str) -> list[dict]:
        out = []
        impression = incident.latest("impression.primary", confirmed_only=True)
        if impression and impression.value not in (None, ""):
            out.append({
                "resourceType": "Condition", "id": f"condition-impression-{impression.id}",
                "verificationStatus": {"coding": [{"system": COND_VER_STATUS, "code": "unconfirmed"}]},
                "code": {"text": str(impression.value)},
                "subject": {"reference": f"Patient/{pid}"},
                "recordedDate": impression.ts.isoformat(),
                "note": [{"text": "EMS crew's stated working impression; not a diagnosis"}],
            })
        seen: set = set()
        for f in incident.history("trauma.injuries", confirmed_only=True):
            for item in (f.value or []):
                if norm_value(item) in seen:
                    continue
                seen.add(norm_value(item))
                out.append({
                    "resourceType": "Condition", "id": f"condition-injury-{f.id}-{_slug(item)}",
                    "verificationStatus": {"coding": [{"system": COND_VER_STATUS, "code": "provisional"}]},
                    "code": {"text": str(item)},
                    "subject": {"reference": f"Patient/{pid}"},
                    "recordedDate": f.ts.isoformat(),
                })
        return out
