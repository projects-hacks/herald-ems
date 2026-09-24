"""County alert checklists end to end, through an Incident: which checklists open, what each needs, the county
scores in the snapshot, the county rule quoted in the alert, and what the relay would send. Santa Clara overrides
trauma, sepsis and STEMI; the generic county uses the defaults in config/checklists.yaml."""
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Role
from herald.relay import Relay


def medic(inc, key, value):
    return inc.ingest(FactIn(key=key, value=value, role=Role.medic, captured_by=CapturedBy.medic, confidence=0.95))


def photo(inc, key, value):
    return inc.ingest(FactIn(key=key, value=value, role=Role.photo, captured_by=CapturedBy.camera, confidence=0.99))


def feed(inc, facts):
    for k, v in facts:
        medic(inc, k, v)
    return inc.snapshot()


def checklist(snap, aid):
    return next(r for r in snap["readiness"] if r["id"] == aid)


def state(snap, aid, key):
    return next(i["state"] for i in checklist(snap, aid)["items"] if i["key"] == key)


ROLLOVER = [("patient.age", 70), ("patient.sex", "M"), ("trauma.mechanism", "rollover MVC, ejected"),
            ("trauma.criteria", ["ejection", "rollover unrestrained"]), ("vitals.sbp", 84), ("vitals.hr", 78),
            ("vitals.rr", 22), ("vitals.spo2", 95), ("vitals.on_oxygen", False), ("vitals.gcs_total", 15)]


# ---------- trauma (Santa Clara Policy 605) ----------
def test_rollover_ejection_sbp_84_at_70_is_a_red_n_and_yellow_o_u_trauma_alert(santa_clara_county):
    inc = Incident(dispatch="vehicle rollover")
    snap = feed(inc, ROLLOVER)
    t = snap["scores"]["trauma_605"]
    assert [c["code"] for c in t["criteria"] if c["state"] == "met"] == ["N.3", "O", "U"]
    assert t["red"] == ["N.3 Age older than 65 years: Systolic BP is less than 110 mmHg (SBP 84, age 70)"]
    assert t["yellow"] == ["O. Auto crash with partial or complete ejection", "U. Rollover with unrestrained occupant"]
    assert (t["met"], t["level"], t["complete"]) == (True, "red", True)
    assert not any(c["state"] == "met" for c in t["criteria"] if c["code"] == "J")     # GCS 15: motor 6
    alert = next(a for a in snap["alerts"] if a["type"] == "trauma_alert_criteria")
    assert alert["level"] == "red" and len(alert["criteria"]) == 3
    assert any("closest open Adult Trauma Center" in r and "602 §VI.C.2" in r for r in alert["county_rule"])
    assert not any("Pediatric" in r for r in alert["county_rule"])
    trauma = checklist(snap, "trauma")
    assert trauma["label"] == "Trauma Alert" and "Policy 605" in trauma["source"]
    assert state(snap, "trauma", "@trauma_605") == "done"
    assert "patient.pregnancy_weeks" not in [i["key"] for i in trauma["items"]]       # male: not relevant
    assert not trauma["ready"] and {i["key"] for i in trauma["items"] if i["state"] == "missing"} == {
        "meds.anticoagulant", "transport.destination", "transport.eta_min"}
    sent = Relay(lambda: inc).critical_values()
    assert sent["score.trauma_605"] == "RED N.3; YELLOW O, U"


def test_trauma_checklist_opens_when_the_score_has_any_criterion(santa_clara_county):
    inc = Incident(dispatch="sick person")
    snap = feed(inc, [("trauma.mechanism", "fell from a roof"), ("trauma.criteria", ["fall over 10 feet"])])
    assert [r["id"] for r in snap["readiness"]] == ["trauma"]
    assert snap["scores"]["trauma_605"]["level"] == "yellow"


def test_a_hypotensive_medical_patient_is_not_a_trauma_alert(santa_clara_county):
    inc = Incident(dispatch="sick person")
    snap = feed(inc, [("patient.age", 70), ("vitals.sbp", 84), ("vitals.hr", 110)])
    assert snap["readiness"] == [] and snap["scores"]["trauma_605"]["applies"] is False
    assert not any(a["type"] == "trauma_alert_criteria" for a in snap["alerts"])
    assert "score.trauma_605" not in Relay(lambda: inc).critical_values()


def test_trauma_county_rules_for_a_child_and_a_pregnant_patient(santa_clara_county):
    inc = Incident(dispatch="pedestrian struck")
    snap = feed(inc, [("patient.age", 8), ("trauma.mechanism", "struck by car"),
                      ("trauma.criteria", ["pelvic fracture"])])
    rules = next(a for a in snap["alerts"] if a["type"] == "trauma_alert_criteria")["county_rule"]
    assert any("Pediatric Trauma Center" in r for r in rules) and not any("Adult Trauma Center" in r for r in rules)
    inc = Incident(dispatch="fall")
    snap = feed(inc, [("patient.age", 29), ("patient.sex", "F"), ("trauma.mechanism", "fall down stairs"),
                      ("trauma.criteria", ["two or more proximal long bone fractures"]),
                      ("patient.pregnancy_weeks", 28)])
    rules = next(a for a in snap["alerts"] if a["type"] == "trauma_alert_criteria")["county_rule"]
    assert any("Level III Neonatal ICU" in r for r in rules)
    assert state(snap, "trauma", "patient.pregnancy_weeks") == "done"


def test_pregnancy_item_is_listed_when_it_could_be_relevant(santa_clara_county):
    inc = Incident(dispatch="fall")
    keys = lambda s: [i["key"] for i in checklist(s, "trauma")["items"]]
    assert "patient.pregnancy_weeks" in keys(inc.snapshot())                    # sex and age not known yet
    assert "patient.pregnancy_weeks" in keys(feed(inc, [("patient.sex", "F"), ("patient.age", 34)]))
    older = Incident(dispatch="fall")
    assert "patient.pregnancy_weeks" not in keys(feed(older, [("patient.sex", "F"), ("patient.age", 81)]))


def test_a_waiting_photo_reading_makes_the_criteria_item_pending(santa_clara_county):
    inc = Incident(dispatch="mvc")
    feed(inc, [("trauma.mechanism", "mvc"), ("patient.age", 40), ("vitals.hr", 80), ("vitals.rr", 16),
               ("vitals.spo2", 97), ("vitals.on_oxygen", False), ("vitals.gcs_motor", 6)])
    photo(inc, "vitals.sbp", 128)                                   # unconfirmed: needs the medic's tap
    snap = inc.snapshot()
    assert state(snap, "trauma", "@trauma_605") == "pending" and state(snap, "trauma", "vitals.sbp") == "pending"
    entry = next(m for m in snap["needs_attention"]["missing"] if m["key"] == "@trauma_605")
    assert entry["pending_confirm"] is True


# ---------- sepsis (Santa Clara 700-A04) ----------
def test_uti_with_fever_tachycardia_tachypnea_meets_sepsis_prenotification(santa_clara_county):
    inc = Incident(dispatch="sick person")
    snap = feed(inc, [("patient.age", 78), ("infection.suspected", "urinary"), ("vitals.temp", 38.6),
                      ("vitals.hr", 112), ("vitals.rr", 24), ("vitals.sbp", 104)])
    s = snap["scores"]["sepsis_700a04"]
    assert (s["met"], s["complete"], s["missing"]) == (True, False, ["EtCO2 (not measured)"])
    sepsis = checklist(snap, "sepsis")
    assert sepsis["label"] == "Sepsis pre-notification" and "Sepsis Alert" not in str(snap["readiness"])
    etco2 = next(i for i in sepsis["items"] if i["key"] == "vitals.etco2")
    assert (etco2["state"], etco2["note"]) == ("missing", "not measured")
    missing = snap["needs_attention"]["missing"]
    assert any(m["key"] == "vitals.etco2" and m.get("note") == "not measured" for m in missing)
    assert state(snap, "sepsis", "vitals.consciousness|vitals.gcs_total") == "missing"
    alert = next(a for a in snap["alerts"] if a["type"] == "sepsis_prenotification")
    assert alert["label"] == "Sepsis pre-notification (700-A04)" and "two or more SIRS" in alert["criteria"][0]
    assert Relay(lambda: inc).critical_values()["score.sepsis_700a04"] == \
        "met (infection: urinary; T 38.6 °C; HR 112; RR 24)"
    snap = feed(inc, [("vitals.gcs_total", 14), ("vitals.etco2", 22)])
    assert snap["scores"]["sepsis_700a04"]["complete"] is True
    assert checklist(snap, "sepsis")["ready"] is True


def test_tachycardia_without_a_suspected_infection_opens_no_sepsis_checklist(santa_clara_county):
    inc = Incident(dispatch="anxiety")
    snap = feed(inc, [("vitals.hr", 124), ("vitals.rr", 26), ("vitals.temp", 37.0)])
    assert not any(r["id"] == "sepsis" for r in snap["readiness"])
    assert snap["scores"]["sepsis_700a04"]["met"] is False
    assert not any(a["type"] == "sepsis_prenotification" for a in snap["alerts"])


# ---------- STEMI (Santa Clara 700-A08) ----------
STEMI = [("ecg.stemi_reading", True), ("symptom.onset", "13:05"), ("ecg.twelve_lead_time", "13:20"),
         ("ecg.transmitted", True), ("vitals.sbp", 142), ("allergies", ["penicillin"])]


def test_stemi_checklist_done_when_the_facts_are_confirmed_including_aspirin(santa_clara_county):
    inc = Incident(dispatch="chest pain")
    snap = feed(inc, STEMI)
    stemi = checklist(snap, "stemi")
    assert [i["key"] for i in stemi["items"]][0] == "ecg.stemi_reading" and stemi["done"] == 6
    aspirin = next(i for i in stemi["items"] if i["key"] == "meds.given[drug=aspirin]")
    assert aspirin["label"] == "Time of aspirin administration"
    assert (aspirin["state"], aspirin["note"]) == ("missing", "not recorded")
    medic(inc, "meds.given", {"drug": "nitroglycerin", "dose": 0.4, "unit": "mg", "route": "SL"})
    assert state(inc.snapshot(), "stemi", "meds.given[drug=aspirin]") == "missing"
    photo(inc, "meds.given", {"drug": "aspirin", "dose": 324})                 # waiting for a tap
    snap = inc.snapshot()
    assert state(snap, "stemi", "meds.given[drug=aspirin]") == "pending"
    waiting = next(m for m in snap["needs_attention"]["missing"] if m["key"] == "meds.given[drug=aspirin]")
    assert waiting["pending_confirm"] is True
    medic(inc, "meds.given", {"drug": "aspirin", "dose": 324, "unit": "mg", "route": "PO", "time": "13:22"})
    snap = inc.snapshot()
    assert checklist(snap, "stemi")["ready"] is True and checklist(snap, "stemi")["done"] == 7


def test_stemi_opens_on_the_monitor_reading_not_on_a_negative_one(santa_clara_county):
    inc = Incident(dispatch="sick person")
    medic(inc, "ecg.stemi_reading", False)
    assert inc.snapshot()["readiness"] == []
    medic(inc, "ecg.stemi_reading", True)
    assert [r["id"] for r in inc.snapshot()["readiness"]] == ["stemi"]


# ---------- the generic county uses the defaults ----------
def test_generic_county_uses_default_checklists_and_no_county_scores(generic_county):
    inc = Incident(dispatch="mvc rollover")
    snap = feed(inc, ROLLOVER)
    assert "trauma_605" not in snap["scores"] and "sepsis_700a04" not in snap["scores"]
    trauma = checklist(snap, "trauma")
    assert trauma["label"] == "Trauma alert" and "@field_triage" in [i["key"] for i in trauma["items"]]
    assert state(snap, "trauma", "@field_triage") == "done"                         # complete (age and SBP)
    assert not any(a["type"] == "trauma_alert_criteria" for a in snap["alerts"])
    assert "score.trauma_605" not in Relay(lambda: inc).critical_values()
    inc = Incident(dispatch="fever")
    snap = feed(inc, [("infection.suspected", "respiratory")])
    sepsis = checklist(snap, "sepsis")
    assert sepsis["label"] == "Suspected sepsis" and "@news2" in [i["key"] for i in sepsis["items"]]
    stemi = checklist(Incident(dispatch="chest pain").snapshot(), "stemi")
    assert [i["key"] for i in stemi["items"]][0] == "symptom.onset"                 # the default STEMI list


def test_stroke_keeps_the_county_checklist_and_opens_on_an_exam(santa_clara_county):
    inc = Incident(dispatch="sick person")
    medic(inc, "exam.gfast.facial", 1)
    snap = inc.snapshot()
    assert [r["id"] for r in snap["readiness"]] == ["stroke"]
    assert [i["key"] for i in snap["readiness"][0]["items"]][:3] == ["vitals.glucose", "stroke.lkw", "@gfast"]
