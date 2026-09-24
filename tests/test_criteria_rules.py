"""Every criterion rule type (herald/scoring/rules.py) and the criteria engine (herald/scoring/criteria.py), on
small hand-written definitions. Each rule is tri-state: met, not met, or undecided because an input is missing
(never guessed)."""
import pytest

from herald.checklists import ChecklistItem
from herald.scoring.criteria import CriteriaScore
from herald.scoring.rules import RULES, evaluate, rule_keys


def met(rule, values):
    return evaluate(rule, values).met


# ---------- comparisons ----------
@pytest.mark.parametrize("x,want", [(5, True), (6, False), (7, False), (None, None)])
def test_below(x, want):
    assert met({"type": "below", "key": "k", "value": 6}, {"k": x} if x is not None else {}) is want


@pytest.mark.parametrize("x,want", [(90, False), (91, True), (None, None)])
def test_above_is_strictly_greater(x, want):
    assert met({"type": "above", "key": "k", "value": 90}, {"k": x} if x is not None else {}) is want


@pytest.mark.parametrize("x,want", [(9, True), (10, False), (29, False), (30, True)])
def test_outside(x, want):
    assert met({"type": "outside", "key": "k", "low": 10, "high": 29}, {"k": x}) is want


@pytest.mark.parametrize("x,want", [(9, False), (10, True), (55, True), (56, False)])
def test_between_is_inclusive(x, want):
    assert met({"type": "between", "key": "k", "low": 10, "high": 55}, {"k": x}) is want


def test_between_with_one_bound():
    assert met({"type": "between", "key": "k", "low": 15}, {"k": 15}) is True
    assert met({"type": "between", "key": "k", "low": 15}, {"k": 14}) is False
    assert met({"type": "between", "key": "k", "high": 9}, {"k": 9}) is True


def test_missing_input_is_undecided_and_named():
    o = evaluate({"type": "above", "key": "vitals.hr", "value": 90}, {})
    assert o.met is None and o.needs == ("vitals.hr",)


# ---------- vital-sign rules ----------
RA = {"type": "room_air_below", "key": "spo2", "oxygen_key": "o2", "value": 90}


def test_room_air_below():
    assert met(RA, {"spo2": 88, "o2": False}) is True
    assert met(RA, {"spo2": 90, "o2": False}) is False
    assert met(RA, {"spo2": 88}) is None                       # room air or oxygen not stated
    o = evaluate(RA, {"spo2": 88, "o2": True})                 # on oxygen: the room-air value is unknown
    assert o.met is None and o.needs == ("spo2",)


SBP = {"type": "sbp_by_age", "age_key": "age", "sbp_key": "sbp", "bands": [
    {"code": "N.1", "age_max": 9, "sbp_below_base": 70, "sbp_below_per_year": 2, "text": "t1"},
    {"code": "N.2", "age_min": 10, "age_max": 64, "sbp_below": 90, "text": "t2"},
    {"code": "N.3", "age_min": 65, "sbp_below": 110, "text": "t3"}]}


@pytest.mark.parametrize("age,sbp,want,code", [
    (5, 79, True, "N.1"), (5, 80, False, "N.1"), (9, 87, True, "N.1"), (9, 88, False, "N.1"),
    (10, 89, True, "N.2"), (10, 90, False, "N.2"), (64, 89, True, "N.2"), (64, 90, False, "N.2"),
    (65, 109, True, "N.3"), (65, 110, False, "N.3"), (70, 84, True, "N.3")])
def test_sbp_by_age_bands(age, sbp, want, code):
    o = evaluate(SBP, {"age": age, "sbp": sbp})
    assert (o.met, o.override["code"]) == (want, code)


def test_sbp_by_age_needs_both_inputs():
    assert evaluate(SBP, {"sbp": 80}).needs == ("age",)
    assert evaluate(SBP, {"age": 40}).needs == ("sbp",)


HR = {"type": "hr_above_sbp", "age_key": "age", "sbp_key": "sbp", "hr_key": "hr", "min_age": 10}


def test_hr_above_sbp():
    assert met(HR, {"age": 40, "sbp": 100, "hr": 101}) is True
    assert met(HR, {"age": 40, "sbp": 100, "hr": 100}) is False
    assert met(HR, {"age": 9, "sbp": 80, "hr": 140}) is False      # below the minimum age: does not apply
    assert evaluate(HR, {"age": 40, "sbp": 100}).needs == ("hr",)


MOTOR = {"type": "motor_gcs_below", "key": "motor", "value": 6, "total_key": "total",
         "motor_min": 1, "motor_max": 6, "others_min": 2, "others_max": 9}


@pytest.mark.parametrize("vals,want", [
    ({"motor": 5}, True), ({"motor": 6}, False),
    ({"motor": 6, "total": 3}, False),                  # a stated motor score wins over the total
    ({"total": 15}, False),                             # 15 = E4 V5 M6
    ({"total": 14}, None), ({"total": 8}, None),        # the total doesn't settle the motor score
    ({"total": 7}, True), ({"total": 3}, True),         # E4 + V5 = 9 at most, so motor <= total - 2 < 6
    ({}, None)])
def test_motor_gcs_below_uses_the_total_only_when_arithmetic_settles_it(vals, want):
    assert met(MOTOR, vals) is want


# ---------- presence, lists, records ----------
def test_present_and_its_negative_words():
    r = {"type": "present", "key": "k", "unless": ["none", "no"]}
    assert met(r, {"k": "warfarin"}) is True
    assert met(r, {"k": "None"}) is False                          # an explicit denial
    assert met(r, {}) is None and met(r, {"k": ""}) is None and met(r, {"k": []}) is None
    assert met(r, {"k": ["none", "apixaban"]}) is True
    assert met({"type": "present", "key": "b", "unless": ["false"]}, {"b": False}) is False
    assert met({"type": "present", "key": "b", "unless": ["false"]}, {"b": True}) is True


def test_present_prefix():
    r = {"type": "present_prefix", "prefix": "exam.race."}
    assert met(r, {"exam.race.arm": 1}) is True
    assert met(r, {"exam.gfast.arm_leg": 1}) is None


def test_contains_cites_the_value_and_never_says_absent():
    r = {"type": "contains", "key": "trauma.criteria", "value": "Pelvic fracture"}
    o = evaluate(r, {"trauma.criteria": ["ejection", "pelvic fracture"]})
    assert o.met is True and o.fields["value"] == "pelvic fracture"
    assert met(r, {"trauma.criteria": ["ejection"]}) is None       # not described is not "no pelvic fracture"
    assert met(r, {}) is None


def test_one_of():
    r = {"type": "one_of", "key": "patient.sex", "values": ["F", "female"]}
    assert met(r, {"patient.sex": "f"}) is True
    assert met(r, {"patient.sex": "M"}) is False
    assert met(r, {}) is None


def test_record_has():
    r = {"type": "record_has", "key": "meds.given", "field": "drug", "values": ["aspirin"]}
    assert met(r, {"meds.given": [{"drug": "nitroglycerin"}, {"drug": "Aspirin", "dose": 324}]}) is True
    assert met(r, {"meds.given": [{"drug": "nitroglycerin"}]}) is None
    assert met(r, {}) is None


# ---------- combinations ----------
def _r(v):     # a leaf that is met / not met / undecided on demand
    return {"type": "present", "key": v, "unless": ["no"]}


@pytest.mark.parametrize("vals,n,want", [
    ({"a": 1, "b": 1}, 2, True),                   # 2 met
    ({"a": 1, "b": "no", "c": "no"}, 2, False),    # 1 met, nothing left to decide
    ({"a": 1, "b": "no"}, 2, None),                # 1 met, c unknown: could still reach 2
    ({"a": 1, "b": 1}, 3, None),
    ({"a": "no", "b": "no"}, 2, False)])           # 0 met, only c unknown: can't reach 2
def test_count_at_least(vals, n, want):
    o = evaluate({"type": "count_at_least", "n": n, "rules": [_r("a"), _r("b"), _r("c")]}, vals)
    assert o.met is want and len(o.parts) == 3


def test_all_of_and_any_of():
    rules = [_r("a"), _r("b")]
    assert met({"type": "all_of", "rules": rules}, {"a": 1, "b": 1}) is True
    assert met({"type": "all_of", "rules": rules}, {"a": 1, "b": "no"}) is False
    assert met({"type": "all_of", "rules": rules}, {"a": 1}) is None
    assert met({"type": "all_of", "rules": rules}, {"b": "no"}) is False     # decided without a
    assert met({"type": "any_of", "rules": rules}, {"b": 1}) is True         # decided without a
    assert met({"type": "any_of", "rules": rules}, {"a": "no", "b": "no"}) is False
    assert met({"type": "any_of", "rules": rules}, {"a": "no"}) is None


def test_rule_keys_and_every_type_is_registered():
    assert rule_keys({"type": "all_of", "rules": [SBP, HR, RA]}) == {"age", "sbp", "hr", "spo2", "o2"}
    assert set(RULES) >= {"below", "above", "outside", "between", "contains", "present", "count_at_least",
                          "all_of", "any_of", "record_has", "one_of", "present_prefix", "room_air_below",
                          "sbp_by_age", "hr_above_sbp", "motor_gcs_below"}


# ---------- the engine ----------
DEF = {
    "id": "t", "name": "T", "kind": "criteria", "source": "src", "county": "x",
    "applies_when": {"type": "present", "key": "injured", "needs": "Injury"},
    "groups": [{"id": "red", "met": True, "short": "RED"}, {"id": "yellow", "met": True, "short": "YEL"},
               {"id": "info", "met": False, "short": "i"}],
    "red": [{"code": "K", "type": "outside", "key": "rr", "low": 10, "high": 29, "required": True,
             "text": "K rr", "finding": "RR {value}", "needs": {"rr": "Respiratory rate"}}],
    "yellow": [{"code": "O", "type": "contains", "key": "crit", "value": "ejection", "text": "O ejection"}],
    "info": [{"code": "X", "type": "present", "key": "ac", "text": "X anticoag", "finding": "{value}"}],
    "relay_text": "{by_group}", "relay_text_not_met": "none met",
}


def test_engine_met_level_complete_and_texts():
    s = CriteriaScore(DEF)
    r = s.evaluate({"injured": "yes", "rr": 8, "crit": ["ejection"], "ac": "warfarin"})
    assert r["red"] == ["K rr (RR 8)"] and r["yellow"] == ["O ejection"] and r["info"] == ["X anticoag (warfarin)"]
    assert (r["met"], r["level"], r["flagged"], r["complete"], r["missing"]) == (True, "red", True, True, [])
    assert s.relay_text(r) == "RED K; YEL O; i X"
    assert [c["state"] for c in r["criteria"]] == ["met", "met", "met"]


def test_engine_info_group_flags_but_is_not_met():
    r = CriteriaScore(DEF).evaluate({"injured": "yes", "rr": 16, "ac": "warfarin"})
    assert (r["met"], r["level"], r["flagged"], r["complete"]) == (False, None, True, True)


def test_engine_missing_required_input_is_incomplete_and_named():
    s = CriteriaScore(DEF)
    r = s.evaluate({"injured": "yes", "crit": ["ejection"]})
    assert (r["met"], r["complete"], r["missing"]) == (True, False, ["Respiratory rate"])
    assert s.relay_text(r) == "YEL O"                         # a met criterion is sent even while incomplete
    r = s.evaluate({"injured": "yes"})
    assert (r["met"], r["complete"]) == (False, False) and s.relay_text(r) is None
    r = s.evaluate({"injured": "yes", "rr": 16})
    assert (r["met"], r["complete"]) == (False, True) and s.relay_text(r) == "none met"


def test_engine_does_not_apply_without_its_precondition():
    s = CriteriaScore(DEF)
    r = s.evaluate({"rr": 8, "crit": ["ejection"]})
    assert (r["applies"], r["met"], r["flagged"], r["red"], r["missing"]) == (False, False, False, [], ["Injury"])
    assert s.relay_text(r) is None


def test_engine_input_keys():
    assert CriteriaScore(DEF).input_keys() == {"injured", "rr", "crit", "ac"}


# ---------- checklist items (record fields, alternatives, scores) ----------
def test_record_field_item():
    it = ChecklistItem.parse(["meds.given[drug=aspirin]", "Time of aspirin administration"])
    aspirin, nitro = {"meds.given": [{"drug": "aspirin", "dose": 324}]}, {"meds.given": [{"drug": "nitroglycerin"}]}
    assert it.state(aspirin, aspirin, {}, {}, set()) == "done"
    assert it.state(nitro, {**aspirin}, {}, {}, set()) == "pending"          # waiting for the medic's tap
    assert it.state(nitro, nitro, {}, {}, set()) == "missing"
    assert it.vocab_keys == ["meds.given"]


def test_alternative_and_score_items():
    gcs = ChecklistItem.parse({"key": "vitals.consciousness|vitals.gcs_total", "label": "Mental status"})
    assert gcs.state({"vitals.gcs_total": 14}, {}, {}, {}, set()) == "done"
    score = ChecklistItem.parse(["@t", "T criteria"])
    assert score.state({}, {}, {"t": {"complete": False, "met": True}}, {}, set()) == "done"     # met decides it
    assert score.state({}, {}, {"t": {"complete": False, "met": False}}, {"t": {"complete": True}}, set()) == "pending"
    assert score.state({}, {}, {"t": {"complete": False}}, {}, {"t"}) == "pending"              # exam started
    assert score.state({}, {}, {}, {}, set()) == "missing"


def test_conditional_item_is_listed_unless_decided_false():
    it = ChecklistItem.parse({"key": "patient.pregnancy_weeks", "label": "Pregnancy (weeks)",
                              "when": {"type": "one_of", "key": "patient.sex", "values": ["F"]}})
    assert it.listed({"patient.sex": "F"}) and it.listed({}) and not it.listed({"patient.sex": "M"})
