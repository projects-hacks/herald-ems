"""FHIR R4 confirmed-record export (X2): herald/reporting/fhir.py, config/fhir_codes.yaml, GET /api/handoff/fhir.
Only confirmed facts ever appear -- the same guarantee the relay and the handoff report already give -- and any
existing drug/allergy code (herald/terminology/) passes straight through instead of being re-invented here."""
from fakes import make_client, tiny_coder
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Role, Status
from herald.core.vocabulary import default_vocabulary
from herald.reporting import FhirExport
from herald.scoring import default_scales

RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"


def said(inc, key, value, conf=0.99, **kw):
    return inc.ingest(FactIn(key=key, value=value, confidence=conf, **kw))


def exporter():
    return FhirExport.from_config(default_vocabulary(), default_scales())


def by_type(bundle, resource_type):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == resource_type]


def test_problems_is_clean_against_the_shipped_vocabulary():
    assert exporter().problems() == []


def test_bundle_shape_covers_every_resource_type():
    inc = Incident("possible stroke")
    name = said(inc, "patient.name", "Jane Doe")          # require_tap: needs an explicit confirm even at conf 0.99
    identifier = said(inc, "patient.identifier", "MRN-123")
    for f in (name, identifier):
        assert f.status == Status.unconfirmed
        inc.set_status(f.id, Status.confirmed)
    said(inc, "patient.age", 68)
    said(inc, "patient.sex", "F")
    said(inc, "impression.primary", "Acute stroke, left-sided weakness")
    said(inc, "vitals.sbp", 150)
    said(inc, "vitals.sbp", 168)      # a second confirmed reading: the trend, not just the latest
    said(inc, "vitals.hr", 92)
    said(inc, "allergies", ["penicillin", "latex"])
    said(inc, "meds.given", {"drug": "aspirin", "dose": 325, "unit": "mg", "route": "PO", "by": "crew"})
    said(inc, "trauma.injuries", ["left facial droop"])

    bundle = exporter().build(inc)
    assert bundle["resourceType"] == "Bundle" and bundle["type"] == "collection"

    patient, = by_type(bundle, "Patient")
    assert patient["id"] == f"patient-{inc.id}"
    assert patient["identifier"] == [{"value": "MRN-123"}]
    assert patient["name"] == [{"text": "Jane Doe"}]
    assert patient["gender"] == "female"

    sbp_obs = [o for o in by_type(bundle, "Observation") if o["code"]["coding"][0]["code"] == "8480-6"]
    assert [o["valueQuantity"]["value"] for o in sbp_obs] == [150, 168]      # both readings, insertion order
    for o in sbp_obs:
        assert o["code"]["coding"][0] == {"system": "http://loinc.org", "code": "8480-6",
                                          "display": "Systolic blood pressure"}
        assert o["valueQuantity"] == {"value": o["valueQuantity"]["value"], "unit": "mmHg",
                                      "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}
        assert o["category"][0]["coding"][0]["code"] == "vital-signs"
        assert o["subject"] == {"reference": f"Patient/{patient['id']}"}

    age_obs, = [o for o in by_type(bundle, "Observation") if o["code"]["coding"][0]["code"] == "30525-0"]
    assert age_obs["valueQuantity"] == {"value": 68, "unit": "years", "system": "http://unitsofmeasure.org", "code": "a"}
    assert age_obs["category"][0]["coding"][0]["code"] == "social-history"

    med, = by_type(bundle, "MedicationAdministration")
    assert med["status"] == "completed"
    assert med["medicationCodeableConcept"] == {"text": "aspirin"}   # no coder wired here: text only, never invented
    assert med["dosage"] == {"dose": {"value": 325, "unit": "mg"}, "route": {"text": "PO"}}
    assert med["note"] == [{"text": "given by crew"}]

    allergy_texts = {a["code"]["text"] for a in by_type(bundle, "AllergyIntolerance")}
    assert allergy_texts == {"penicillin", "latex"}
    assert all(a["clinicalStatus"]["coding"][0]["code"] == "active" for a in by_type(bundle, "AllergyIntolerance"))

    condition_texts = {c["code"]["text"] for c in by_type(bundle, "Condition")}
    assert condition_texts == {"Acute stroke, left-sided weakness", "left facial droop"}
    impression = next(c for c in by_type(bundle, "Condition") if c["code"]["text"].startswith("Acute stroke"))
    assert impression["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    assert "not a diagnosis" in impression["note"][0]["text"]


def test_unconfirmed_facts_never_appear_in_the_bundle():
    inc = Incident("possible stroke")
    said(inc, "vitals.sbp", 150)                                             # confirmed: medic, high confidence
    said(inc, "vitals.hr", 200, captured_by=CapturedBy.camera, role=Role.photo)  # camera: born unconfirmed
    said(inc, "allergies", ["penicillin"])
    unconfirmed_dose = inc.ingest(FactIn(key="meds.given",
                                         value={"drug": "morphine", "dose": 4, "unit": "mg", "by": "crew"},
                                         confidence=0.1))                    # below auto-confirm: unconfirmed
    assert unconfirmed_dose.status == Status.unconfirmed
    hr_fact = next(f for f in inc.facts if f.key == "vitals.hr")
    assert hr_fact.status == Status.unconfirmed

    bundle = exporter().build(inc)
    assert by_type(bundle, "Observation")                                    # sbp is still there
    assert not any(o["code"]["coding"][0]["code"] == "8867-4" for o in by_type(bundle, "Observation"))
    assert not by_type(bundle, "MedicationAdministration")                   # the only dose was unconfirmed

    reject = inc.set_status(hr_fact.id, Status.rejected)
    assert reject.status == Status.rejected
    assert not any(o["code"]["coding"][0]["code"] == "8867-4" for o in by_type(exporter().build(inc), "Observation"))


def test_existing_drug_and_allergy_coding_passes_through_unchanged():
    coder = tiny_coder()
    dose, = coder.code([FactIn(key="meds.given", value={"drug": "Narcan", "dose": 4, "unit": "mg", "route": "IN"})])
    # penicillin resolves to the NEMSIS drug-class allergy code (ICD-10-CM), codeine to its own RxNorm ingredient
    # code (test_terminology.py test_allergies_get_rxnorm_or_the_drug_class_code_and_never_become_medications) --
    # this test only needs to show BOTH systems pass through untouched, not re-derive the coder's own matching.
    allergy, = coder.code([FactIn(key="allergies", value=["penicillin", "Codeine"])])
    inc = Incident("possible stroke")
    inc.ingest(dose.model_copy(update={"confidence": 0.99}))
    inc.ingest(allergy.model_copy(update={"confidence": 0.99}))

    bundle = exporter().build(inc)
    med, = by_type(bundle, "MedicationAdministration")
    assert med["medicationCodeableConcept"]["coding"] == [{"system": RXNORM, "code": "7242", "display": "naloxone"}]
    by_text = {a["code"]["text"]: a["code"]["coding"] for a in by_type(bundle, "AllergyIntolerance")}
    assert by_text["penicillin"] == [{"system": ICD10CM, "code": "Z88.0", "display": "penicillin"}]
    assert by_text["codeine"] == [{"system": RXNORM, "code": "2670", "display": "codeine"}]


def test_get_handoff_fhir_endpoint_matches_the_incident(tmp_path):
    client, ctx = make_client()
    # /api/facts is the device-panel endpoint (herald/api/capture.py structured()): it always starts unconfirmed
    # and requires the medic's explicit tap, same as a real monitor reading would.
    added = client.post("/api/facts", json=[{"key": "vitals.sbp", "value": 140}]).json()
    client.post(f"/api/facts/{added[0]['id']}/confirm")
    r = client.get("/api/handoff/fhir")
    assert r.status_code == 200
    body = r.json()
    assert body["resourceType"] == "Bundle"
    patient, = by_type(body, "Patient")
    assert patient["id"] == f"patient-{ctx.incident.id}"
    assert any(o["code"]["coding"][0]["code"] == "8480-6" for o in by_type(body, "Observation"))
