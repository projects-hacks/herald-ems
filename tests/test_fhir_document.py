"""The handoff as a FHIR R4 document (herald/reporting/fhir_document.py, config/fhir_codes.yaml `document`,
GET /api/handoff/fhir). Checks the FHIR document rules (R4 Bundle bdl-9/10/11, documents.html: identifier,
timestamp, Composition first, fullUrl on every entry), that every reference resolves inside the bundle, that the
Composition sections are the handoff report's own sections, and that nothing waiting for a tap carries a value."""
import json
import re

from fakes import make_client
from fakes import test_settings as settings_for
from herald.api.context import build_handoff
from herald.checklists import ChecklistEngine
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Role, Status
from herald.core.snapshot import default_counties
from herald.core.vocabulary import default_vocabulary
from herald.reporting import FhirDocument, FhirExport, default_handoff_config
from herald.scoring import default_scales

FHIR_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
XHTML_DIV = re.compile(r'^<div xmlns="http://www.w3.org/1999/xhtml">.*</div>$', re.S)


def document(unit="Medic 25"):
    vocab, scales = default_vocabulary(), default_scales()
    handoff = build_handoff(default_handoff_config(), vocab, scales, ChecklistEngine.from_config(default_counties()),
                            settings_for())
    return FhirDocument.from_config(FhirExport.from_config(vocab, scales), handoff, unit)


def said(inc, key, value, conf=0.99, **kw):
    return inc.ingest(FactIn(key=key, value=value, confidence=conf, **kw))


def stroke_call():
    inc = Incident("possible stroke")
    for k, v in [("patient.age", 68), ("patient.sex", "F"), ("complaint.chief", "left-sided weakness"),
                 ("impression.primary", "stroke"), ("vitals.sbp", 182), ("vitals.dbp", 104), ("vitals.hr", 92),
                 ("vitals.hr", 104), ("vitals.spo2", 95), ("meds.anticoagulant", "warfarin"),
                 ("transport.destination", "Regional"), ("transport.eta_min", 12)]:
        said(inc, k, v)
    said(inc, "allergies", "none", speaker="husband", role=Role.family)            # coerced to [] (no allergies)
    # the daughter contradicts him: her answer waits for the medic's choice and must never carry a value out
    said(inc, "allergies", ["aspirin"], speaker="daughter", role=Role.family)
    return inc


def resources(bundle, rtype=None):
    return [e["resource"] for e in bundle["entry"] if rtype is None or e["resource"]["resourceType"] == rtype]


def references(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "reference" and isinstance(v, str):
                yield v
            else:
                yield from references(v)
    elif isinstance(node, list):
        for v in node:
            yield from references(v)


def test_config_is_complete():
    assert document().problems() == []


def test_bundle_follows_the_fhir_document_rules():
    b = document().build(stroke_call())
    assert b["resourceType"] == "Bundle" and b["type"] == "document"
    assert b["identifier"]["system"] and b["identifier"]["value"]                  # bdl-9
    assert b["timestamp"]                                                          # bdl-10
    assert b["entry"][0]["resource"]["resourceType"] == "Composition"              # bdl-11
    urls = [e["fullUrl"] for e in b["entry"]]
    assert len(urls) == len(set(urls))                                             # bdl-7: unique fullUrl
    for e in b["entry"]:
        r = e["resource"]
        assert FHIR_ID.match(r["id"]), r["id"]                                     # no underscores from Herald ids
        assert e["fullUrl"].endswith(f"/{r['resourceType']}/{r['id']}")


def test_every_reference_resolves_inside_the_bundle():
    b = document().build(stroke_call())
    present = {f"{r['resourceType']}/{r['id']}" for r in resources(b)}
    missing = [ref for ref in references(b) if ref not in present]
    assert missing == []


def test_composition_mirrors_the_handoff_report():
    doc, inc = document(), stroke_call()
    report = doc.handoff.build(inc)
    comp = document().build(inc)["entry"][0]["resource"]
    assert comp["type"]["coding"] == [{"system": "http://loinc.org", "code": "34133-9",
                                       "display": "Summary of episode note"}]
    assert comp["status"] == "preliminary" and "attester" not in comp       # assembled, not signed by the crew
    assert comp["title"] == report["format"]["title"] == "Medical handover (SBAR)"
    titles = [s["title"] for s in comp["section"]]
    expected = [s["label"] for s in report["sections"] if s["lines"]]
    assert titles[1:1 + len(expected)] == expected                         # after "How this document was assembled"
    for sec in comp["section"]:
        assert XHTML_DIV.match(sec["text"]["div"])
    situation = next(s for s in comp["section"] if s["title"] == "S: Situation")
    assert "68-year-old female" in situation["text"]["div"]
    assessment = next(s for s in comp["section"] if s["title"] == "A: Assessment")
    hr_obs = [f"Observation/{o['id']}" for o in resources(document().build(inc), "Observation")
              if o["code"]["coding"][0]["code"] == "8867-4"]
    assert hr_obs and set(hr_obs) <= {e["reference"] for e in assessment["entry"]}


def test_trauma_call_gets_the_mist_sections():
    inc = Incident("fall")
    for k, v in [("patient.age", 72), ("patient.sex", "M"), ("trauma.mechanism", "fall 15 feet from a ladder"),
                 ("trauma.injuries", ["open femur fracture"]), ("vitals.sbp", 84), ("vitals.hr", 118)]:
        said(inc, k, v)
    comp = document().build(inc)["entry"][0]["resource"]
    titles = [s["title"] for s in comp["section"]]
    assert comp["title"] == "Trauma handover (MIST)"
    assert {"M: Mechanism", "I: Injuries", "S: Signs"} <= set(titles)


def test_waiting_facts_are_named_never_valued():
    b = document().build(stroke_call())
    comp = b["entry"][0]["resource"]
    waiting = next(s for s in comp["section"] if s["title"].startswith("Not yet confirmed"))
    assert "Allergies" in waiting["text"]["div"]
    text = json.dumps(b)
    assert "aspirin" not in text
    assert "AllergyIntolerance" not in text                    # the confirmed answer is "none": no allergy resource


def test_provenance_names_who_said_and_who_confirmed():
    inc = Incident("possible stroke")
    said(inc, "vitals.sbp", 150)                                             # the medic's clear speech: auto
    hr = inc.ingest(FactIn(key="vitals.hr", value=200, captured_by=CapturedBy.camera, role=Role.photo,
                           speaker="monitor", confidence=0.99, provenance={"photo_id": "ph_1"}))
    assert hr.status == Status.unconfirmed
    inc.set_status(hr.id, Status.confirmed)
    b = document().build(inc)
    provs = {p["target"][0]["reference"]: p for p in resources(b, "Provenance")}
    hr_obs = next(o for o in resources(b, "Observation") if o["code"]["coding"][0]["code"] == "8867-4")
    p = provs[f"Observation/{hr_obs['id']}"]
    codes = {a["type"]["coding"][0]["code"]: a["who"] for a in p["agent"]}
    assert codes["assembler"]["reference"].startswith("Device/")
    assert codes["informant"] == {"display": "monitor (photo)"}
    assert codes["verifier"] == {"display": "medic"}
    assert p["entity"] == [{"role": "source", "what": {"display": "photo ph_1"}}]
    sbp_obs = next(o for o in resources(b, "Observation") if o["code"]["coding"][0]["code"] == "8480-6")
    auto = provs[f"Observation/{sbp_obs['id']}"]
    assert "verifier" not in {a["type"]["coding"][0]["code"] for a in auto["agent"]}   # no tap, no claimed verifier


def test_encounter_is_the_field_transport_to_the_confirmed_destination():
    b = document().build(stroke_call())
    enc, = resources(b, "Encounter")
    assert enc["class"] == {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "FLD",
                            "display": "field"}
    assert enc["status"] == "in-progress"
    assert enc["hospitalization"]["destination"] == {"display": "Regional"}
    assert enc["type"] == [{"text": "EMS response: possible stroke"}]
    dev, = resources(b, "Device")
    assert dev["note"] == [{"text": "Herald on Medic 25"}]


def test_endpoint_defaults_to_the_document_and_keeps_the_collection():
    client, ctx = make_client()
    added = client.post("/api/facts", json=[{"key": "vitals.sbp", "value": 140}]).json()
    client.post(f"/api/facts/{added[0]['id']}/confirm")
    doc = client.get("/api/handoff/fhir").json()
    assert doc["type"] == "document" and doc["entry"][0]["resource"]["resourceType"] == "Composition"
    assert client.get("/api/handoff/fhir?type=collection").json()["type"] == "collection"
    assert client.get("/api/handoff/fhir?format=mist").json()["entry"][0]["resource"]["title"] == \
        "Trauma handover (MIST)"
    assert client.get("/api/handoff/fhir?type=xml").status_code == 400
    assert client.get("/api/handoff/fhir?format=nope").status_code == 400


def test_important_values_are_bold_and_gaps_are_not():
    inc = Incident("fall")
    for k, v in [("patient.age", 72), ("patient.sex", "M"), ("trauma.mechanism", "fall 15 feet from a ladder"),
                 ("vitals.sbp", 84), ("vitals.dbp", 50), ("vitals.hr", 118), ("meds.anticoagulant", "apixaban")]:
        said(inc, k, v)
    divs = {s["title"]: s["text"]["div"] for s in document().build(inc)["entry"][0]["resource"]["section"]}
    assert "<b>BP 84/50 mmHg</b>" in divs["S: Signs"]
    assert "<b>HR 118/min</b>" in divs["S: Signs"]
    assert "<b>Anticoagulant: apixaban</b>" in divs["Allergies, medications, history"]
    assert "<b>Trauma Alert criteria (Policy 605) met</b>" in divs["Alert and patient"]       # met alert
    assert "<li>RR: not yet known</li>" in divs["S: Signs"] or "<li>Respiratory rate: not yet known</li>" in \
        divs["S: Signs"]                                                                       # a gap stays plain
    assert "<b>NEWS2" not in divs["S: Signs"]                                                  # not in emphasis
    assert "<li>72-year-old male</li>" in divs["Alert and patient"]                            # not a vital


def test_emphasis_typo_is_a_startup_problem():
    doc = document()
    doc.cfg = {**doc.cfg, "emphasis": ["vitals.hrr", "@nope"]}
    assert len([p for p in doc.problems() if "emphasis" in p]) == 2
