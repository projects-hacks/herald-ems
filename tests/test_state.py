from herald.extract_rules import extract
from herald.schema import CapturedBy, FactIn, Role, Status
from herald.state import Incident


def feed(inc, text, **kw):
    return [inc.ingest(f) for f in extract(text, **kw)]


def test_gap_first_stroke_checklist_starts_at_zero():
    inc = Incident(dispatch="possible stroke")
    snap = inc.snapshot()
    r = snap["readiness"][0]
    assert (r["label"], r["done"], r["total"]) == ("Stroke alert", 0, 6)
    assert any(u["key"] == "meds.anticoagulant" for u in snap["needs_attention"]["unknown"])


def test_stroke_demo_flow_reaches_ready_and_race_6():
    inc = Incident(dispatch="possible stroke")
    feed(inc, "68-year-old female, sudden left-sided weakness, husband says she was fine at 1:40.")
    feed(inc, "Mild left facial droop, left arm and leg can't lift, eyes deviated to the right, no agnosia.")
    feed(inc, "Onset was witnessed. BP 182 over 104, pulse 92, SpO2 95 on room air, respirations 18, temp 37.1, alert.")
    snap = inc.snapshot()
    assert snap["scores"]["race"]["score"] == 6 and snap["scores"]["race"]["positive"] is True
    assert snap["scores"]["news2"]["complete"] is True
    before = snap["readiness"][0]["done"]
    feed(inc, "Anticoagulant warfarin. Glucose 142.")
    snap = inc.snapshot()
    assert snap["readiness"][0]["ready"] is True and before < 6
    assert any(c["id"] == "lkw" for c in snap["clocks"])


def test_contradiction_from_other_speaker_needs_confirm():
    inc = Incident(dispatch="stroke")
    feed(inc, "Husband says no allergies.")
    [f] = feed(inc, "Mom's allergic to aspirin.", captured_by=CapturedBy.other,
               default_role=Role.family, default_speaker="daughter")
    assert f.status == Status.unconfirmed
    snap = inc.snapshot()
    alert = next(a for a in snap["alerts"] if a["type"] == "contradiction")
    assert [x["speaker"] for x in alert["facts"]] == ["husband", "daughter"]
    inc.set_status(alert["confirm_fact_id"], Status.confirmed)
    assert not any(a["type"] == "contradiction" for a in inc.snapshot()["alerts"])


def test_scores_use_confirmed_facts_only():
    inc = Incident()
    inc.ingest(FactIn(key="vitals.spo2", value=88, captured_by=CapturedBy.camera, confidence=0.99))
    assert "vitals.spo2" not in inc.values(confirmed_only=True)
    assert "SpO2 (scale 1)" in inc.snapshot()["scores"]["news2"]["missing"]


def test_news2_rise_alert():
    inc = Incident(dispatch="stroke")
    feed(inc, "BP 182 over 104, pulse 92, SpO2 95 on room air, respirations 18, temp 37.1, alert.")
    feed(inc, "Pulse 104, breathing 22, sat 94, temp 38.4.")
    snap = inc.snapshot()
    rise = next(a for a in snap["alerts"] if a["type"] == "news2_rise")
    assert rise["to"] >= 5 and rise["band"] == "medium"
