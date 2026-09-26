"""The handoff as a FHIR R4 document (GET /api/handoff/fhir): one Bundle a receiving system can file as a whole.

A FHIR document (https://hl7.org/fhir/R4/documents.html) is a Bundle of type "document" whose first entry is a
Composition. Here the Composition's sections are the handoff report's own sections (MIST for trauma, SBAR for
medical calls, config/handoff.yaml), so the electronic copy and the read-aloud report cannot disagree: each section's
narrative is the report's lines, and its entries point at the coded resources behind those lines. After the
Composition come the same confirmed-only resources as the collection export (FhirExport.sourced), the Encounter for
this transport, the Device that assembled the document, and one Provenance per resource: who said it, who confirmed
it and when, and which clip or photo it came from.

Nothing new is decided here. The report text comes from HandoffBuilder, the resources from FhirExport, the codes
from config/fhir_codes.yaml `document`. Facts waiting for the crew's tap are named (never valued) in their own
section, exactly as the report lists them.
"""
from __future__ import annotations

from html import escape
from typing import Any, Optional

from ..config import load_yaml
from ..core.schema import Status, utcnow
from .fhir import FhirExport, fhir_id

XHTML = "http://www.w3.org/1999/xhtml"
_REQUIRED = ("base_url", "identifier_system", "status", "type", "encounter_class", "participant_system",
             "device_name", "words")
_WORDS = ("about_title", "about", "unit_unknown", "dispatch", "audio", "photo", "confirmed_by")


def _ref(r: dict) -> str:
    return f"{r['resourceType']}/{r['id']}"


def _narrative(items: list, source: Optional[str] = None) -> dict:
    """FHIR Narrative: XHTML in a div with the XHTML namespace, every value escaped (R4 §2.4 Narrative). An item is
    a string, or (text, bold) for a line the reader should find at a glance (`<b>` is allowed narrative XHTML)."""
    def li(item) -> str:
        text, bold = item if isinstance(item, tuple) else (item, False)
        return f"<li><b>{escape(text)}</b></li>" if bold else f"<li>{escape(text)}</li>"
    body = "<ul>" + "".join(li(t) for t in items) + "</ul>" if items else ""
    if source:
        body += f"<p>Source: {escape(source)}</p>"
    return {"status": "generated", "div": f'<div xmlns="{XHTML}">{body}</div>'}


class FhirDocument:
    def __init__(self, export: FhirExport, handoff, codes: dict, unit_id: Optional[str] = None):
        self.export, self.handoff, self.unit_id = export, handoff, unit_id
        self.cfg = codes.get("document", {})

    @classmethod
    def from_config(cls, export: FhirExport, handoff, unit_id: Optional[str] = None,
                    rel: str = "fhir_codes.yaml") -> "FhirDocument":
        return cls(export, handoff, load_yaml(rel), unit_id)

    def problems(self) -> list[str]:
        out = [f"fhir_codes.yaml: document.{k} is missing" for k in _REQUIRED if k not in self.cfg]
        words = self.cfg.get("words", {})
        out += [f"fhir_codes.yaml: document.words.{k} is missing" for k in _WORDS if k not in words]
        for k in self.cfg.get("emphasis", []):
            known = k[1:] in self.export.scales if k.startswith("@") else k in self.export.vocab.keys
            if not known:
                out.append(f"fhir_codes.yaml: document.emphasis {k} is not a vocabulary key or score")
        return out

    # ---------- the document ----------
    def build(self, incident, format_id: Optional[str] = None) -> dict:
        with incident.lock:
            report = self.handoff.build(incident, format_id)
            pid = self.export.patient_id(incident)
            sourced = self.export.sourced(incident, pid)
            device = self._device()
            encounter, encounter_facts = self._encounter(incident, pid)
            by_fact: dict[str, list[str]] = {}
            for r, facts in sourced + [(encounter, encounter_facts)]:
                for f in facts:
                    by_fact.setdefault(f.id, []).append(_ref(r))
            present = {_ref(r) for r, _ in sourced}
            composition = self._composition(incident, report, pid, encounter, device, by_fact, present)
            provenance = [self._provenance(r, facts, device, incident)
                          for r, facts in sourced + [(encounter, encounter_facts)] if facts]
            resources = [composition] + [r for r, _ in sourced] + [encounter, device] + provenance
            base = self.cfg["base_url"].rstrip("/")
            return {
                "resourceType": "Bundle", "id": fhir_id("handoff", incident.id),
                "identifier": {"system": self.cfg["identifier_system"],
                               "value": f"{incident.id}/{report['as_of']}"},
                "type": "document",
                "timestamp": utcnow().isoformat(),
                "entry": [{"fullUrl": f"{base}/{_ref(r)}", "resource": r} for r in resources],
            }

    def _emphasized(self, line: dict, scores: dict) -> bool:
        """Bold a line that states a confirmed value of a key in `document.emphasis` (vitals, allergies,
        anticoagulant) or a score in it that is positive / met (an alert criterion). Never bold: a "not yet known"
        line, a trend series, an incomplete or negative score. Bold marks a value the receiver must not miss."""
        if line["status"] != "confirmed" or not set(line["keys"]) & set(self.cfg.get("emphasis", [])):
            return False
        if line["kind"] == "fact":
            return True
        if line["kind"] == "score":
            r = scores.get(line["keys"][0][1:], {})
            return r.get("positive") is True or r.get("met") is True
        return False

    # ---------- resources ----------
    def _composition(self, incident, report: dict, pid: str, encounter: dict, device: dict,
                     by_fact: dict[str, list[str]], present: set[str]) -> dict:
        words, hwords = self.cfg["words"], self.handoff.cfg.words
        scores = incident.snapshot()["scores"]           # the same confirmed-only results the report used
        sections = [{"title": words["about_title"],
                     "text": _narrative([words["about"]], report["format"]["source"])}]
        for sec in report["sections"]:
            if not sec["lines"]:
                continue
            refs: list[str] = []
            for ln in sec["lines"]:
                for fid in ln["fact_ids"]:
                    refs += by_fact.get(fid, [])
                refs += [r for k in ln["keys"] if k.startswith("@")
                         for r in [f"Observation/{self.export.score_id(k[1:], incident)}"] if r in present]
            section: dict[str, Any] = {"title": sec["label"],
                                       "text": _narrative([(ln["text"], self._emphasized(ln, scores)) for ln in sec["lines"]],
                                                          sec.get("source"))}
            if refs:
                section["entry"] = [{"reference": r} for r in dict.fromkeys(refs)]
            sections.append(section)
        if report["not_yet_known"]:
            sections.append({"title": hwords["missing_heading"],
                             "text": _narrative([g["text"] for g in report["not_yet_known"]])})
        apart = [x["label"] for x in report.get("not_obtained", []) if not x.get("inline")]
        if apart:
            sections.append({"title": hwords["not_obtained_heading"], "text": _narrative(apart)})
        if report["not_yet_confirmed"]:
            sections.append({"title": hwords["unconfirmed_heading"],
                             "text": _narrative([u["label"] + (f" ({hwords['differs']})" if u["differs"] else "")
                                                 for u in report["not_yet_confirmed"]])})
        return {
            "resourceType": "Composition", "id": fhir_id("composition", incident.id),
            "status": self.cfg["status"],
            "type": {"coding": [dict(self.cfg["type"])], "text": report["format"]["title"]},
            "subject": {"reference": f"Patient/{pid}"},
            "encounter": {"reference": _ref(encounter)},
            "date": report["as_of"],
            "author": [{"reference": _ref(device)}],
            "title": report["format"]["title"],
            "section": sections,
        }

    def _encounter(self, incident, pid: str) -> tuple[dict, list]:
        r: dict[str, Any] = {"resourceType": "Encounter", "id": fhir_id("encounter", incident.id),
                             "status": "finished" if incident.ended_at else "in-progress",
                             "class": dict(self.cfg["encounter_class"]),
                             "subject": {"reference": f"Patient/{pid}"},
                             "period": {"start": incident.started.isoformat()}}
        if incident.ended_at:
            r["period"]["end"] = incident.ended_at.isoformat()
        if incident.dispatch:
            r["type"] = [{"text": self.cfg["words"]["dispatch"].format(dispatch=incident.dispatch)}]
        destination = incident.latest("transport.destination", confirmed_only=True)
        if destination and destination.value not in (None, ""):
            r["hospitalization"] = {"destination": {"display": str(destination.value)}}
            return r, [destination]
        return r, []

    def _device(self) -> dict:
        unit = self.unit_id or self.cfg["words"]["unit_unknown"]
        return {"resourceType": "Device", "id": fhir_id("herald", self.unit_id or "unit"),
                "deviceName": [{"name": self.cfg["device_name"], "type": "user-friendly-name"}],
                "note": [{"text": f"{self.cfg['device_name']} on {unit}"}]}

    def _provenance(self, target: dict, facts: list, device: dict, incident) -> dict:
        system, words = self.cfg["participant_system"], self.cfg["words"]
        agent = lambda code, who: {"type": {"coding": [{"system": system, "code": code}]}, "who": who}  # noqa: E731
        agents = [agent("assembler", {"reference": _ref(device)})]
        seen: set[tuple[str, str]] = set()
        entities: list[dict] = []
        for f in facts:
            said_by = f"{f.speaker} ({f.role.value})" if f.speaker else f.role.value
            confirmer = self._confirmed_by(incident, f.id)
            for code, who in (("informant", said_by), ("verifier", confirmer)):
                if who and (code, who) not in seen:
                    seen.add((code, who))
                    agents.append(agent(code, {"display": who}))
            for kind, media in (("audio", f.provenance.audio_id), ("photo", f.provenance.photo_id)):
                if media:
                    entities.append({"role": "source", "what": {"display": words[kind].format(id=media)}})
        r: dict[str, Any] = {"resourceType": "Provenance", "id": fhir_id("prov", target["id"]),
                             "target": [{"reference": _ref(target)}],
                             "recorded": max(f.ts for f in facts).isoformat(),
                             "agent": agents}
        if entities:
            r["entity"] = entities
        return r

    def _confirmed_by(self, incident, fact_id: str) -> Optional[str]:
        """Who tapped confirm, from the incident's audit log. A fact confirmed by the policy on ingest (the medic's
        own clear speech) has no tap and so names no verifier: the Provenance does not claim one."""
        for entry in reversed(incident.audit_log):
            if (entry.get("action") == "fact_status_changed" and entry.get("fact_id") == fact_id
                    and entry.get("to") == Status.confirmed.value):
                return self.cfg["words"]["confirmed_by"].format(actor=entry.get("actor", "medic"))
        return None
