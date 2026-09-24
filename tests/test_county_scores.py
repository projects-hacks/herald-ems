"""Santa Clara's own criteria scores, loaded from config/scores/: Policy 605 Trauma Alert criteria and the 700-A04
sepsis pre-notification rule. Every threshold is tested at its boundary, and every criterion quotes the county."""
import pytest

from herald.core.vocabulary import default_vocabulary
from herald.scoring import default_scales

SC = default_scales()
T, SEP = SC["trauma_605"], SC["sepsis_700a04"]
INJURED = {"trauma.mechanism": "fall"}
NORMAL = {**INJURED, "patient.age": 40, "vitals.sbp": 130, "vitals.hr": 80, "vitals.rr": 16, "vitals.spo2": 98,
          "vitals.on_oxygen": False, "vitals.gcs_motor": 6}


def codes(r, group):
    return [c["code"] for c in r["criteria"] if c["group"] == group and c["state"] == "met"]


# ---------- Policy 605 ----------
def test_trauma_605_cites_the_county_and_every_criterion_has_its_letter():
    assert T.county == "santa_clara" and "Policy 605" in T.d["source"] and "2025-04-01" in T.d["source"]
    for g in T.groups:
        for c in T.d.get(g["id"], []):
            assert c["code"] and c["text"].startswith(c["code"].split("-")[0][:1]), c
    assert {g["id"]: g["met"] for g in T.groups} == {"red": True, "yellow": True, "consider": False, "burn": False}


def test_every_trauma_criteria_value_is_used_and_exists():
    enum = set(default_vocabulary().meta("trauma.criteria")["enum"])
    used = set()

    def walk(rule):
        if rule.get("key") == "trauma.criteria":
            used.add(rule["value"])
        for r in rule.get("rules", ()):
            walk(r)
    for g in T.groups:
        for c in T.d.get(g["id"], []):
            walk(c)
    assert used <= enum, used - enum
    assert used == enum, f"vocabulary values with no Policy 605 criterion: {enum - used}"


def test_normal_injured_patient_is_complete_and_not_met():
    r = T.evaluate(NORMAL)
    assert (r["applies"], r["met"], r["complete"], r["flagged"], r["missing"]) == (True, False, True, False, [])
    assert T.relay_text(r) == "no Policy 605 criterion met"


def test_not_injured_means_policy_605_does_not_apply():
    r = T.evaluate({k: v for k, v in NORMAL.items() if k != "trauma.mechanism"} | {"vitals.sbp": 80})
    assert (r["applies"], r["met"], r["red"]) == (False, False, [])
    assert "injured patients" in r["missing"][0] and T.relay_text(r) is None


@pytest.mark.parametrize("age,sbp,code", [(5, 79, "N.1"), (9, 87, "N.1"), (10, 89, "N.2"), (64, 89, "N.2"),
                                          (65, 109, "N.3"), (80, 109, "N.3")])
def test_605_n_sbp_by_age_met(age, sbp, code):
    r = T.evaluate({**NORMAL, "patient.age": age, "vitals.sbp": sbp, "vitals.hr": 60})
    assert codes(r, "red") == [code] and r["level"] == "red"


@pytest.mark.parametrize("age,sbp", [(5, 80), (9, 88), (10, 90), (64, 90), (65, 110)])
def test_605_n_sbp_by_age_not_met_at_the_limit(age, sbp):
    assert codes(T.evaluate({**NORMAL, "patient.age": age, "vitals.sbp": sbp, "vitals.hr": 60}), "red") == []


def test_605_n4_hr_above_sbp_from_age_10():
    assert codes(T.evaluate({**NORMAL, "vitals.sbp": 100, "vitals.hr": 101}), "red") == ["N.4"]
    assert codes(T.evaluate({**NORMAL, "vitals.sbp": 100, "vitals.hr": 100}), "red") == []
    assert codes(T.evaluate({**NORMAL, "patient.age": 9, "vitals.sbp": 100, "vitals.hr": 140}), "red") == []


@pytest.mark.parametrize("rr,hit", [(9, True), (10, False), (29, False), (30, True)])
def test_605_k_respiratory_rate(rr, hit):
    assert codes(T.evaluate({**NORMAL, "vitals.rr": rr}), "red") == (["K"] if hit else [])


@pytest.mark.parametrize("spo2,o2,state", [(89, False, "met"), (90, False, "not_met"), (85, True, "unknown")])
def test_605_m_room_air_spo2(spo2, o2, state):
    r = T.evaluate({**NORMAL, "vitals.spo2": spo2, "vitals.on_oxygen": o2})
    assert next(c["state"] for c in r["criteria"] if c["code"] == "M") == state
    assert r["complete"] is (state != "unknown")
    if state == "unknown":
        assert r["missing"] == ["SpO2 on room air"]


@pytest.mark.parametrize("vals,state", [({"vitals.gcs_motor": 5}, "met"), ({"vitals.gcs_motor": 6}, "not_met"),
                                        ({"vitals.gcs_total": 15}, "not_met"), ({"vitals.gcs_total": 7}, "met"),
                                        ({"vitals.gcs_total": 12}, "unknown")])
def test_605_j_motor_gcs(vals, state):
    base = {k: v for k, v in NORMAL.items() if k != "vitals.gcs_motor"}
    r = T.evaluate({**base, **vals})
    assert next(c["state"] for c in r["criteria"] if c["code"] == "J") == state
    if state == "unknown":
        assert r["missing"] == ["Motor GCS (or GCS total)"]


def test_605_injury_patterns_mechanisms_and_procedures():
    r = T.evaluate({**NORMAL, "trauma.criteria": ["pelvic fracture", "fall over 10 feet"]})
    assert codes(r, "red") == ["E"] and codes(r, "yellow") == ["W"] and r["level"] == "red"
    assert r["red"] == ["E. Suspected pelvic fracture"]
    assert codes(T.evaluate({**NORMAL, "procedures.done": [{"procedure": "tourniquet"}]}), "red") == ["I"]
    assert codes(T.evaluate({**NORMAL, "procedures.done": [{"procedure": "bvm ventilation"}]}), "red") == ["L"]
    assert codes(T.evaluate({**NORMAL, "procedures.done": [{"procedure": "iv access"}]}), "red") == []


def test_605_r_child_unrestrained_needs_age_0_to_9():
    child = {**NORMAL, "trauma.criteria": ["child unrestrained"], "vitals.hr": 90}
    assert codes(T.evaluate({**child, "patient.age": 9, "vitals.sbp": 100}), "yellow") == ["R"]
    assert codes(T.evaluate({**child, "patient.age": 10}), "yellow") == []


def test_605_yellow_alone_is_still_a_trauma_alert():
    """Policy 602 §VI.C: Yellow criteria make a Trauma Alert Patient in Santa Clara."""
    r = T.evaluate({**NORMAL, "trauma.criteria": ["ejection"]})
    assert (r["met"], r["level"], r["red"]) == (True, "yellow", []) and T.relay_text(r) == "YELLOW O"


def test_605_special_considerations_are_shown_but_not_a_trauma_alert():
    r = T.evaluate({**NORMAL, "meds.anticoagulant": "apixaban",
                    "trauma.criteria": ["low level fall with significant head impact"]})
    assert codes(r, "consider") == ["X.1", "X.6"] and (r["met"], r["flagged"]) == (False, True)
    assert "X.1 Patients with minor traumatic injuries also on anti-coagulants" in r["consider"][0]
    assert codes(T.evaluate({**NORMAL, "meds.anticoagulant": "none"}), "consider") == []


def test_605_x7_pregnant_beyond_20_weeks_in_cardiac_arrest():
    arrest = {**NORMAL, "procedures.done": [{"procedure": "cpr"}]}
    assert codes(T.evaluate({**arrest, "patient.pregnancy_weeks": 21}), "consider") == ["X.7"]
    assert codes(T.evaluate({**arrest, "patient.pregnancy_weeks": 20}), "consider") == []
    assert codes(T.evaluate({**NORMAL, "patient.pregnancy_weeks": 30}), "consider") == []


def test_605_major_burn_is_its_own_group_not_a_trauma_alert():
    r = T.evaluate({**NORMAL, "trauma.criteria": ["major burn"]})
    assert codes(r, "burn") == ["III.A"] and (r["met"], r["level"], r["flagged"]) == (False, None, True)
    assert "designated burn center" in r["burn"][0]


# ---------- 700-A04 ----------
def test_sepsis_700a04_cites_the_county_and_never_says_sepsis_alert():
    assert SEP.county == "santa_clara" and "700-A04" in SEP.d["source"] and "2026-01-01" in SEP.d["source"]
    assert "Sepsis Alert" not in SEP.name and "pre-notification" in SEP.name
    assert "two or more SIRS criteria are met" in SEP.d["thresholds_text"]


def sirs(r):
    [top] = r["criteria"]
    count = next(p for p in top["parts"] if p["code"] == "1.3")
    return {p["code"]: p["state"] for p in count["parts"]}


@pytest.mark.parametrize("temp,state", [(35.5, "met"), (35.6, "not_met"), (38.0, "not_met"), (38.1, "met")])
def test_sepsis_temperature_boundaries_in_celsius(temp, state):
    """< 96 °F (35.56 °C) or > 100.4 °F (38.0 °C)."""
    assert sirs(SEP.evaluate({"vitals.temp": temp}))["1.3.1"] == state


@pytest.mark.parametrize("key,value,state", [("vitals.hr", 90, "not_met"), ("vitals.hr", 91, "met"),
                                             ("vitals.rr", 20, "not_met"), ("vitals.rr", 21, "met"),
                                             ("vitals.etco2", 25, "not_met"), ("vitals.etco2", 24, "met")])
def test_sepsis_hr_rr_etco2_boundaries(key, value, state):
    code = {"vitals.hr": "1.3.2", "vitals.rr": "1.3.3", "vitals.etco2": "1.3.4"}[key]
    assert sirs(SEP.evaluate({key: value}))[code] == state


def test_sepsis_two_criteria_with_suspected_infection_is_met_even_without_etco2():
    r = SEP.evaluate({"infection.suspected": "urinary", "vitals.temp": 38.6, "vitals.hr": 112, "vitals.rr": 24})
    assert (r["met"], r["complete"], r["missing"]) == (True, False, ["EtCO2 (not measured)"])
    assert sirs(r)["1.3.4"] == "unknown"                           # not measured, never "not met"
    assert SEP.relay_text(r) == "met (infection: urinary; T 38.6 °C; HR 112; RR 24)"


def test_sepsis_needs_a_suspected_infection():
    r = SEP.evaluate({"vitals.temp": 38.6, "vitals.hr": 112, "vitals.rr": 24})
    assert (r["met"], r["complete"]) == (False, False) and "Suspected infection (source)" in r["missing"]
    assert SEP.relay_text(r) is None


def test_sepsis_one_criterion_is_not_met_once_everything_is_measured():
    r = SEP.evaluate({"infection.suspected": "respiratory", "vitals.temp": 37.0, "vitals.hr": 104, "vitals.rr": 18,
                      "vitals.etco2": 34})
    assert (r["met"], r["complete"], r["missing"]) == (False, True, [])
    assert SEP.relay_text(r) == "not met"


def test_every_key_a_criteria_score_reads_is_in_the_vocabulary():
    vocab = default_vocabulary()
    for sid in SC.ids():
        if SC[sid].d["kind"] == "criteria":
            assert SC[sid].input_keys() <= set(vocab.keys), (sid, SC[sid].input_keys() - set(vocab.keys))
    assert {"vitals.gcs_total", "procedures.done", "patient.pregnancy_weeks"} <= T.input_keys()


def test_county_scores_only_for_their_county():
    assert {"trauma_605", "sepsis_700a04"} <= set(SC.ids("santa_clara"))
    assert not {"trauma_605", "sepsis_700a04"} & set(SC.ids("generic"))
    assert {"news2", "race", "gfast", "field_triage"} <= set(SC.ids("generic"))
