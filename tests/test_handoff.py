"""The written handoff report (herald/reporting/, config/handoff.yaml): format choice, section order, confirmed facts
only, missing items shown as missing, events in order with provenance, scores with their source, determinism, and
GET /api/handoff."""
from __future__ import annotations

import pytest

from fakes import make_client
from fakes import test_settings as settings_for
from herald.api.context import build_handoff
from herald.checklists import ChecklistEngine
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Role
from herald.core.snapshot import default_counties
from herald.core.vocabulary import default_vocabulary
from herald.reporting import LINE_KINDS, HandoffConfig, default_handoff_config
from herald.scoring import default_scales

MONITOR = {"captured_by": "device", "role": "device", "speaker": "monitor", "confidence": 0.99,
           "provenance": {"extractor": "manual"}}


def builder(**settings):
    return build_handoff(default_handoff_config(), default_vocabulary(), default_scales(),
                         ChecklistEngine.from_config(default_counties()), settings_for(**settings))


def said(inc: Incident, key, value, conf=0.99, **kw):
    return inc.ingest(FactIn(key=key, value=value, confidence=conf, **kw))


def trauma_call() -> Incident:
    inc = Incident("fall, chest pain")
    for k, v in [("patient.age", 72), ("patient.sex", "F"), ("complaint.chief", "chest pain"),
                 ("trauma.mechanism", "fall 15 feet from a ladder"), ("trauma.criteria", ["fall over 10 feet"]),
                 ("vitals.sbp", 84), ("vitals.dbp", 50), ("vitals.hr", 118), ("vitals.spo2", 91),
                 ("vitals.on_oxygen", False), ("vitals.gcs_total", 14), ("meds.anticoagulant", "apixaban"),
                 ("ecg.stemi_reading", True), ("ecg.transmitted", True)]:
        said(inc, k, v)
    said(inc, "meds.given", {"drug": "naloxone", "dose": 2, "unit": "mg", "route": "IN", "by": "fire"})
    said(inc, "meds.given", {"drug": "aspirin", "dose": 324, "unit": "mg", "route": "PO", "time": "1405",
                             "by": "crew"})
    said(inc, "procedures.done", {"procedure": "IV access", "detail": "18 g left AC"})
    return inc


def section(report, sid):
    return next(s for s in report["sections"] if s["id"] == sid)


def texts(report, sid):
    return [ln["text"] for ln in section(report, sid)["lines"]]


def all_lines(report):
    return [ln for s in report["sections"] for ln in s["lines"]]


# ---------- the content ----------
@pytest.mark.parametrize("county", ["santa_clara", "generic"])
def test_real_config_is_valid_for_every_county(county):
    reg = default_counties()
    before = reg.active["id"]
    reg.activate(county)
    try:
        cfg = HandoffConfig.from_config()
        ids = ChecklistEngine.from_config(reg).ids()
        assert cfg.problems(default_vocabulary(), default_scales(), LINE_KINDS, ids) == []
    finally:
        reg.activate(before)
    assert {"mist", "medical"} <= set(cfg.formats)
    assert cfg.select[0] == {"format": "mist", "checklists": ["trauma"]} and cfg.default == "medical"
    for f in cfg.formats.values():
        assert "Policy 501" in f["source"] and f["title"] and f["label"]
        assert all(s.get("source") for s in f["sections"])
    assert "Wood K" in cfg.formats["mist"]["source"] and "Leonard M" in cfg.formats["medical"]["source"]
    assert [s["id"] for s in cfg.formats["mist"]["sections"]][:5] == [
        "opening", "mechanism", "injuries", "signs", "treatment"]
    assert [s["id"] for s in cfg.formats["medical"]["sections"]][:5] == [
        "opening", "situation", "background", "assessment", "treatment"]


def test_bad_content_is_refused_at_startup():
    raw = {"formats": {"x": {"label": "X", "title": "X", "source": "s", "sections": [
        {"id": "a", "label": "A", "lines": [{"kind": "fact", "templates": ["{vitals.nope}"]},
                                            {"kind": "score", "score": "nope"},
                                            {"kind": "fact", "templates": ["{vitals.hr}"], "required": ["zzz"]},
                                            {"kind": "magic"}]}]}},
           "select": [{"format": "y", "checklists": ["trauma"]}], "default": "x", "words": {},
           "value_text": {}, "score_text": {}, "time_format": "%H:%M"}
    errs = HandoffConfig.from_dict(raw).problems(default_vocabulary(), default_scales(), LINE_KINDS,
                                                 ["trauma", "stroke"])
    joined = " | ".join(errs)
    for needle in ("vitals.nope", "unknown score 'nope'", "unknown checklist 'zzz'", "unknown line kind 'magic'",
                   "unknown format 'y'", "words: missing missing"):
        assert needle in joined, needle


def test_score_engines_expose_their_input_keys():
    s = default_scales()
    assert "vitals.rr" in s["news2"].input_keys() and "exam.gfast.gaze" in s["gfast"].input_keys()
    assert s["gfast"].max_score == 4
    t = s["trauma_605"]
    result = t.evaluate({"trauma.mechanism": "fall", "vitals.sbp": 84, "patient.age": 72})
    assert len(t.criteria_keys()) == len(result["criteria"])
    n3 = next(keys for (g, keys), row in zip(t.criteria_keys(), result["criteria"]) if row["code"] == "N.3")
    assert {"vitals.sbp", "patient.age"} <= n3


# ---------- format choice and order ----------
def test_trauma_call_gets_mist_in_order(santa_clara_county):
    inc = trauma_call()
    r = builder().build(inc)
    assert r["format"]["id"] == "mist" and r["selected_by"] == "checklist:trauma"
    assert texts(r, "mechanism") == ["fall 15 feet from a ladder"]
    inj = texts(r, "injuries")
    assert inj[0] == "Injuries found: not yet known"
    assert any(t.startswith("Policy 605 Red N.3") and "SBP 84, age 72" in t for t in inj)
    assert any(t.startswith("Policy 605 Yellow W.") for t in inj)
    signs = texts(r, "signs")
    assert signs[:4] == ["BP 84/50 mmHg", "HR 118/min", "Respiratory rate: not yet known", "SpO2 91% on room air"]
    assert "GCS 14" in signs and "12-lead reads STEMI, transmitted" in signs
    assert texts(r, "treatment") == ["naloxone 2 mg IN, by fire", "aspirin 324 mg PO at 14:05, by crew",
                                     "IV access 18 g left AC"]
    opening = texts(r, "opening")
    assert opening[0] == "Trauma Alert criteria (Policy 605) met"          # 501 §IV.D: the alert first
    assert "72-year-old female" in opening and "Chief complaint: chest pain" in opening
    text = r["text"]
    order = [text.index(x) for x in ("met;", "M: Mechanism", "I: Injuries", "S: Signs", "T: Treatment")]
    assert order == sorted(order)


def test_generic_county_mist_uses_the_national_field_triage(generic_county):
    r = builder().build(trauma_call())
    assert r["format"]["id"] == "mist"
    assert any(t.startswith("Field triage 2021 Red SBP 84 < 110") for t in texts(r, "injuries"))
    assert "Field triage (2021) met" in texts(r, "opening")


def test_medical_call_gets_sbar_and_shows_what_is_missing(santa_clara_county):
    inc = Incident("possible stroke")
    said(inc, "patient.age", 67)
    said(inc, "vitals.sbp", 168)
    r = builder().build(inc)
    assert r["format"]["id"] == "medical" and r["selected_by"] == "default"
    assert [s["id"] for s in r["sections"]][:5] == ["opening", "situation", "background", "assessment", "treatment"]
    sit = texts(r, "situation")
    assert "Last known well: not yet known" in sit and "67-year-old, sex not yet known" in sit
    assert "Glucose: not yet known" in texts(r, "assessment")              # required while stroke is open
    assert texts(r, "treatment") == ["none recorded"]
    assert section(r, "treatment")["lines"][0]["status"] == "empty"
    missing = [ln for ln in all_lines(r) if ln["status"] == "missing"]
    assert missing and all(ln["fact_ids"] == [] and ln["text"].endswith("not yet known") for ln in missing)
    gaps = [g["label"] for g in r["not_yet_known"]]
    assert "Stroke screen (G.F.A.S.T.)" in gaps                            # checklist item no line covers
    assert "Last known well" not in gaps                                   # already shown in its place
    assert r["text"].startswith("Medical handover (SBAR).")


def test_format_can_be_requested(santa_clara_county):
    b = builder()
    r = b.build(trauma_call(), "medical")
    assert r["format"]["id"] == "medical" and r["selected_by"] == "request"
    with pytest.raises(KeyError):
        b.build(trauma_call(), "soap")


# ---------- confirmed facts only ----------
def test_unconfirmed_facts_never_appear_in_a_line(santa_clara_county):
    inc = trauma_call()
    photo = said(inc, "allergies", ["penicillin"], captured_by=CapturedBy.camera, role=Role.photo)
    low = said(inc, "vitals.rr", 34, conf=0.2)
    r = builder().build(inc)
    ids = {i for ln in all_lines(r) for i in ln["fact_ids"]}
    assert photo.id not in ids and low.id not in ids
    assert "penicillin" not in r["text"] and "34" not in r["text"]
    waiting = {u["key"]: u for u in r["not_yet_confirmed"]}
    assert waiting["allergies"]["fact_ids"] == [photo.id] and "value" not in waiting["allergies"]
    assert "Respiratory rate: not yet known" not in texts(r, "signs")     # heard, waiting: not "unknown"
    assert "Not yet confirmed, left out of this report: Allergies; Respiratory rate." in r["text"]


def test_a_contradicting_value_is_flagged_not_mixed_in(santa_clara_county):
    inc = trauma_call()
    said(inc, "meds.anticoagulant", "none", captured_by=CapturedBy.other, speaker="daughter")
    r = builder().build(inc)
    assert "Anticoagulant: apixaban" in texts(r, "history")
    u = next(x for x in r["not_yet_confirmed"] if x["key"] == "meds.anticoagulant")
    assert u["differs"] is True and "Anticoagulant (differs from the value in this report)" in r["text"]


def test_rejected_facts_are_gone(santa_clara_county):
    inc = trauma_call()
    f = said(inc, "vitals.hr", 180)
    inc.set_status(f.id, inc.facts[0].status.__class__("rejected"))
    assert "HR 118/min" in texts(builder().build(inc), "signs")


# ---------- events, provenance, scores ----------
def test_events_are_listed_in_order_with_who_and_when(santa_clara_county):
    inc = Incident("fall")
    a = said(inc, "meds.given", {"drug": "epinephrine", "dose": 0.15, "unit": "mg", "route": "IM"})
    b = said(inc, "meds.given", {"drug": "epinephrine", "dose": 0.15, "unit": "mg", "route": "IM"})   # said again
    c = said(inc, "procedures.done", {"procedure": "splint", "by": "fire"})
    said(inc, "meds.given", {"drug": "fentanyl", "dose": 50, "unit": "mcg", "route": "IV"}, conf=0.3)  # waiting
    r = builder().build(inc)
    lines = section(r, "treatment")["lines"]
    assert [ln["text"] for ln in lines] == ["epinephrine 0.15 mg IM", "splint, by fire"]
    assert lines[0]["fact_ids"] == [a.id, b.id] and lines[1]["fact_ids"] == [c.id]
    src = lines[0]["sources"][0]
    assert src["role"] == "medic" and src["captured_by"] == "medic" and len(src["time"]) == 5 and src["ts"]
    assert [u["key"] for u in r["not_yet_confirmed"]] == ["meds.given"]


def test_score_lines_carry_their_source_and_facts(santa_clara_county):
    inc = trauma_call()
    for k, v in [("vitals.rr", 24), ("vitals.consciousness", "A"), ("vitals.temp", 37.0)]:
        said(inc, k, v)
    r = builder().build(inc)
    news2 = next(ln for ln in section(r, "signs")["lines"] if ln["text"].startswith("NEWS2"))
    assert news2["text"].endswith("risk (RCP 2017)") and "Royal College of Physicians" in news2["source"]
    by_id = {f.id: f.key for f in inc.facts}
    assert {by_id[i] for i in news2["fact_ids"]} <= default_scales()["news2"].input_keys()
    n3 = next(ln for ln in section(r, "injuries")["lines"] if "N.3" in ln["text"])
    assert {"vitals.sbp", "patient.age"} <= {by_id[i] for i in n3["fact_ids"]}
    assert "Policy 605" in n3["source"]


def test_an_incomplete_score_shows_no_partial_total(santa_clara_county):
    r = builder().build(trauma_call())
    news2 = next(t for t in texts(r, "signs") if t.startswith("NEWS2"))
    assert news2 == "NEWS2 incomplete: Respiratory rate, Consciousness, Temperature not yet known (RCP 2017)"


def test_record_items_are_never_listed_as_missing(santa_clara_county):
    inc = Incident("chest pain")
    said(inc, "ecg.stemi_reading", True)
    r = builder().build(inc)
    assert "stemi" in r["open_checklists"]
    assert all("aspirin" not in g["label"].lower() for g in r["not_yet_known"])
    assert "aspirin" not in r["text"].lower()


def test_a_fallback_template_leaves_the_rest_a_gap(santa_clara_county):
    inc = Incident("chest pain")
    said(inc, "ecg.transmitted", True)                 # the reading itself was never said
    r = builder().build(inc)
    assert "12-lead transmitted" in texts(r, "assessment")
    assert '12-lead reads "STEMI" or "Acute MI Suspected"' in [g["label"] for g in r["not_yet_known"]]


def test_unit_id_and_eta_open_the_report(santa_clara_county):
    inc = trauma_call()
    eta = said(inc, "transport.eta_min", 11)
    r = builder(unit_id="Medic 25").build(inc)
    opening = section(r, "opening")["lines"]
    assert opening[2]["text"] == "Medic 25 en route" and opening[2]["fact_ids"] == []
    assert opening[3]["text"].startswith("ETA 11 min (said at ") and opening[3]["fact_ids"] == [eta.id]


def test_text_is_deterministic(santa_clara_county):
    inc = trauma_call()
    b = builder()
    one, two = b.build(inc), b.build(inc)
    assert one == two
    lists = bool(one["not_yet_known"]) + bool(one["not_yet_confirmed"])
    assert len(one["text"].splitlines()) == 1 + len([s for s in one["sections"] if s["lines"]]) + lists


# ---------- API ----------
def test_api_handoff_and_snapshot_summary():
    c, _ = make_client()
    c.post("/api/incident", json={"dispatch": "fall"})
    c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 84, **MONITOR},
                               {"key": "vitals.hr", "value": 118, **MONITOR}])
    r = c.get("/api/handoff")
    assert r.status_code == 200
    body = r.json()
    assert body["format"]["id"] == "mist" and "HR 118/min" in body["text"]
    assert {f["id"] for f in body["formats"]} >= {"mist", "medical"}
    hr = next(ln for ln in all_lines(body) if ln["text"] == "HR 118/min")
    assert hr["sources"][0]["speaker"] == "monitor" and hr["sources"][0]["role"] == "device"
    assert c.get("/api/handoff?format=medical").json()["format"]["id"] == "medical"
    bad = c.get("/api/handoff?format=soap")
    assert bad.status_code == 400 and "mist" in bad.json()["detail"]
    summary = c.get("/api/state").json()["handoff"]
    assert summary["format"] == "mist" and summary["lines"] >= 2 and summary["unconfirmed"] == 0
    assert set(summary) == {"format", "label", "selected_by", "lines", "missing", "unconfirmed"}


# ---------- approved keys (2026-09-24): impression, time of injury, airway, territory, triage, before arrival ----------
def test_impression_opens_the_report_in_both_formats(santa_clara_county):
    inc = trauma_call()
    b = builder()
    assert "Primary impression: not yet known" in texts(b.build(inc), "opening")      # 501 §III.A.2 required
    f = said(inc, "impression.primary", "hip fracture after fall")
    mist = texts(b.build(inc), "opening")
    assert mist.index("72-year-old female") < mist.index("Impression: hip fracture after fall") \
        < mist.index("Chief complaint: chest pain")
    line = next(ln for ln in section(b.build(inc), "opening")["lines"] if ln["text"].startswith("Impression"))
    assert line["fact_ids"] == [f.id]
    assert "Impression: hip fracture after fall" in texts(b.build(inc, "medical"), "opening")


def test_time_of_injury_follows_the_age_in_mist(santa_clara_county):
    inc = trauma_call()
    b = builder()
    assert "Time of injury: not yet known" in texts(b.build(inc), "opening")
    said(inc, "trauma.injury_time", "1402")
    opening = texts(b.build(inc), "opening")
    assert opening[opening.index("72-year-old female") + 1] == "Injured at 14:02"            # ATMIST: A, then T
    assert "Injured at 14:02" in texts(b.build(inc, "medical"), "situation")
    medical = Incident("possible stroke")
    assert not any("injury" in t.lower() for t in texts(b.build(medical), "situation"))    # not asked of a stroke


def test_airway_status_leads_the_signs(santa_clara_county):
    inc = trauma_call()
    said(inc, "airway.status", "patent with adjunct")
    assert texts(builder().build(inc), "signs")[0] == "Airway: patent with adjunct"


def test_territory_is_read_with_the_stemi_reading(santa_clara_county):
    inc = trauma_call()
    said(inc, "ecg.territory", ["inferior", "lateral"])
    r = builder().build(inc)
    assert "12-lead reads STEMI, inferior, lateral (700-A08 §3.2)" in texts(r, "opening")
    assert "12-lead reads STEMI, inferior, lateral, transmitted" in texts(r, "signs")
    alone = Incident("chest pain")
    said(alone, "ecg.territory", ["inferior"])
    r = builder().build(alone)
    assert "12-lead territory inferior" in texts(r, "assessment")
    assert '12-lead reads "STEMI" or "Acute MI Suspected"' in [g["label"] for g in r["not_yet_known"]]


def test_triage_category_needs_a_tap_then_opens_the_report(santa_clara_county):
    inc = trauma_call()
    f = said(inc, "triage.category", "immediate")
    b = builder()
    r = b.build(inc)
    assert "immediate" not in r["text"]
    assert [u["key"] for u in r["not_yet_confirmed"]] == ["triage.category"]
    inc.set_status(f.id, f.status.__class__("confirmed"))
    opening = texts(b.build(inc), "opening")
    assert opening.index("Triage: immediate (SALT)") == 2                   # after the two alert statements
    assert opening.index("Triage: immediate (SALT)") < opening.index("72-year-old female")


def test_before_arrival_care_is_its_own_section(santa_clara_county):
    inc = Incident("fall")
    fire = said(inc, "meds.given", {"drug": "naloxone", "dose": 2, "unit": "mg", "route": "IN", "by": "fire",
                                    "before_arrival": True})
    said(inc, "procedures.done", {"procedure": "c-collar", "by": "fire", "before_arrival": True})
    b = builder()
    r = b.build(inc)
    assert texts(r, "treatment") == ["none recorded"]                        # nothing by this crew yet
    assert texts(r, "before_arrival") == ["naloxone 2 mg IN, by fire", "c-collar, by fire"]
    assert section(r, "before_arrival")["lines"][0]["fact_ids"] == [fire.id]
    said(inc, "meds.given", {"drug": "fentanyl", "dose": 50, "unit": "mcg", "route": "IV", "time": "1422",
                             "by": "crew", "before_arrival": False})
    said(inc, "meds.given", {"drug": "ondansetron", "dose": 4, "unit": "mg", "route": "IV"})   # not stated: crew
    r = b.build(inc)
    assert texts(r, "treatment") == ["fentanyl 50 mcg IV at 14:22, by crew", "ondansetron 4 mg IV"]
    assert "T: Treatment: fentanyl" in r["text"] and "\nBefore arrival: naloxone 2 mg IN, by fire; c-collar, by fire." \
        in r["text"]
    order = [s["id"] for s in r["sections"]]
    assert order.index("before_arrival") == order.index("treatment") + 1
    assert texts(b.build(inc, "medical"), "before_arrival") == ["naloxone 2 mg IN, by fire", "c-collar, by fire"]


def test_events_filter_checks_its_fields():
    kind = LINE_KINDS["events"]
    spec = {"kind": "events", "key": "meds.given", "parts": ["{drug}"], "where": {"prior": True}}
    assert kind.problems(spec, default_vocabulary(), default_scales(), default_handoff_config()) == [
        "meds.given has no field 'prior'"]
    assert kind.keep({"where_not": {"before_arrival": True}}, {"drug": "aspirin"})
    assert not kind.keep({"where": {"before_arrival": True}}, {"drug": "aspirin"})
