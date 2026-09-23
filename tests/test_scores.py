"""The scores are arithmetic from published tables (config/scores/*.yaml), so we prove the loaded tables
exhaustively at every band boundary. If any of these fail, the score shown to a medic is wrong."""
import pytest

from herald.scoring import default_scales

SC = default_scales()
N2 = SC["news2"]


class S:  # the published calculators, read through the registry
    news2_rr = staticmethod(lambda v: N2.points("vitals.rr", v))
    news2_spo2_scale1 = staticmethod(lambda v: N2.points("vitals.spo2", v))
    news2_sbp = staticmethod(lambda v: N2.points("vitals.sbp", v))
    news2_hr = staticmethod(lambda v: N2.points("vitals.hr", v))
    news2_temp = staticmethod(lambda v: N2.points("vitals.temp", v))
    news2_consciousness = staticmethod(lambda v: N2.points("vitals.consciousness", v))
    news2_oxygen = staticmethod(lambda v: N2.points("vitals.on_oxygen", v))
    news2 = staticmethod(N2.evaluate)
    race = staticmethod(SC["race"].evaluate)
    gfast = staticmethod(SC["gfast"].evaluate)
    field_triage = staticmethod(SC["field_triage"].evaluate)


@pytest.mark.parametrize("rr,pts", [(8, 3), (9, 1), (11, 1), (12, 0), (20, 0), (21, 2), (24, 2), (25, 3)])
def test_news2_rr(rr, pts):
    assert S.news2_rr(rr) == pts


@pytest.mark.parametrize("v,pts", [(91, 3), (92, 2), (93, 2), (94, 1), (95, 1), (96, 0), (100, 0)])
def test_news2_spo2(v, pts):
    assert S.news2_spo2_scale1(v) == pts


@pytest.mark.parametrize("v,pts", [(90, 3), (91, 2), (100, 2), (101, 1), (110, 1), (111, 0), (219, 0), (220, 3)])
def test_news2_sbp(v, pts):
    assert S.news2_sbp(v) == pts


@pytest.mark.parametrize("v,pts", [(40, 3), (41, 1), (50, 1), (51, 0), (90, 0), (91, 1), (110, 1), (111, 2), (130, 2), (131, 3)])
def test_news2_hr(v, pts):
    assert S.news2_hr(v) == pts


@pytest.mark.parametrize("v,pts", [(35.0, 3), (35.1, 1), (36.0, 1), (36.1, 0), (38.0, 0), (38.1, 1), (39.0, 1), (39.1, 2)])
def test_news2_temp(v, pts):
    assert S.news2_temp(v) == pts


def test_news2_consciousness_and_oxygen():
    assert S.news2_consciousness("A") == 0
    for x in ("C", "V", "P", "U"):
        assert S.news2_consciousness(x) == 3
    assert S.news2_oxygen(True) == 2 and S.news2_oxygen(False) == 0


BASE = {"vitals.rr": 18, "vitals.spo2": 97, "vitals.on_oxygen": False, "vitals.sbp": 130,
        "vitals.hr": 80, "vitals.consciousness": "A", "vitals.temp": 37.0}


def test_news2_all_normal_is_low_zero():
    r = S.news2(BASE)
    assert (r["score"], r["band"], r["complete"]) == (0, "low", True)


def test_news2_bands():
    assert S.news2({**BASE, "vitals.rr": 22, "vitals.hr": 104, "vitals.spo2": 94})["band"] == "low"   # 2+1+1 = 4
    r = S.news2({**BASE, "vitals.rr": 22, "vitals.hr": 104, "vitals.spo2": 94, "vitals.temp": 38.4})
    assert (r["score"], r["band"]) == (5, "medium")
    r = S.news2({**BASE, "vitals.consciousness": "C"})
    assert (r["score"], r["band"]) == (3, "low-medium")        # single parameter scoring 3
    assert S.news2({**BASE, "vitals.sbp": 88, "vitals.rr": 26, "vitals.on_oxygen": True})["band"] == "high"


def test_news2_missing_input_is_incomplete_never_guessed():
    vals = dict(BASE)
    vals.pop("vitals.temp")
    r = S.news2(vals)
    assert r["complete"] is False and r["band"] == "incomplete" and "Temperature" in r["missing"]


def test_race_threshold_and_completeness():
    items = {"exam.race.facial": 1, "exam.race.arm": 2, "exam.race.leg": 2, "exam.race.gaze": 1,
             "exam.race.aphasia_agnosia": 0}
    r = S.race(items)
    assert (r["score"], r["positive"], r["complete"]) == (6, True, True)
    r = S.race({**items, "exam.race.leg": 0, "exam.race.arm": 1})
    assert (r["score"], r["positive"]) == (3, False)
    partial = dict(items)
    partial.pop("exam.race.gaze")
    assert S.race(partial)["positive"] is None
    assert S.race({**items, "exam.race.gaze": 5})["parts"]["Head and gaze deviation"]["points"] == 1  # clamped


def test_field_triage_age_adjusted():
    assert "SBP 105 < 110 (age ≥ 65)" in S.field_triage({"patient.age": 70, "vitals.sbp": 105})["red"]
    assert S.field_triage({"patient.age": 40, "vitals.sbp": 105})["red"] == []
    assert any("HR 120 > SBP 100" in x for x in S.field_triage({"patient.age": 40, "vitals.sbp": 100, "vitals.hr": 120})["red"])
    assert S.field_triage({"patient.age": 5, "vitals.sbp": 79})["red"] == ["SBP 79 < 70 + 2×age (80)"]
    assert S.field_triage({"meds.anticoagulant": "warfarin"})["yellow"] == ["Anticoagulant use (warfarin)"]
    assert S.field_triage({"meds.anticoagulant": "none"})["yellow"] == []
    assert S.field_triage({"vitals.spo2": 88, "vitals.on_oxygen": False})["red"] == ["Room-air SpO2 88% (< 90%)"]


def test_gfast_is_four_binary_items_positive_only_at_four():
    items = {"exam.gfast.gaze": 1, "exam.gfast.facial": 1, "exam.gfast.arm_leg": 1, "exam.gfast.speech": 1}
    r = S.gfast(items)
    assert (r["score"], r["positive"], r["complete"]) == (4, True, True)
    assert S.gfast({**items, "exam.gfast.gaze": 0})["positive"] is False
    assert S.gfast({k: v for k, v in items.items() if k != "exam.gfast.speech"})["positive"] is None
    assert "700-A13" in r["source"]


def test_every_score_definition_cites_a_source():
    for sid in SC.ids():
        assert SC[sid].d.get("source"), sid
