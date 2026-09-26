"""The handoff report read like a paramedic's handover (config/handoff.yaml, real config): short spoken criteria with
their values and the citation kept in the JSON, no score bookkeeping, trends only when they moved by the
config/trends.yaml rules, no empty sections, each thing said once; and "unable to obtain" for required items
(POST /api/handoff/not-obtained, core/not_obtained.py): report, snapshot, audit and persistence."""
from __future__ import annotations

import copy

import pytest

from fakes import make_client
from herald.api.encounters import decode_call, encode_call
from herald.checklists import ChecklistEngine
from herald.core import not_obtained as unobtainable
from herald.core.incident import Incident, IncidentEnded
from herald.core.snapshot import default_counties
from herald.core.trends import TrendRules
from herald.core.vocabulary import default_vocabulary
from herald.reporting import LINE_KINDS, HandoffConfig
from herald.scoring import default_scales
from test_handoff import MONITOR, all_lines, builder, said, section, texts


def rollover() -> Incident:
    """The live trauma call: rollover with ejection, HR 132 then 142, SBP 78, motor GCS 5."""
    inc = Incident("rollover")
    for k, v in [("patient.age", 34), ("patient.sex", "M"), ("complaint.chief", "rollover with ejection"),
                 ("trauma.criteria", ["ejection"]), ("vitals.hr", 132), ("vitals.sbp", 78), ("vitals.dbp", 40),
                 ("vitals.gcs_motor", 5), ("vitals.rr", 28), ("vitals.spo2", 93), ("vitals.hr", 142)]:
        said(inc, k, v)
    return inc


# ---------- criteria: short spoken phrases, citation in the JSON ----------
def test_policy_criteria_are_said_briefly_with_their_values(santa_clara_county):
    r = builder().build(rollover())
    inj = texts(r, "injuries")
    assert "Trauma alert: HR above systolic (142 over 78)" in inj
    assert "Trauma alert: not following commands (motor 5)" in inj
    assert "Trauma alert: low systolic for age (78, age 34)" in inj
    assert "Trauma alert: ejection" in inj
    assert "Policy 605" not in r["text"] and "Age 10 and older" not in r["text"]
    n4 = next(ln for ln in section(r, "injuries")["lines"] if ln.get("criterion", {}).get("code") == "N.4")
    assert n4["criterion"] == {"score": "trauma_605", "code": "N.4", "cite": "Policy 605 N.4",
                               "text": "N.4 Age 10 and older: Heart rate is greater than Systolic BP (HR 142, SBP 78)"}
    assert "Policy 605" in n4["source"]
    assert {src["key"] for src in n4["sources"]} == {"patient.age", "vitals.sbp", "vitals.hr"}
    assert texts(r, "opening")[0] == "Trauma alert"


def test_a_criterion_met_from_the_gcs_total_says_the_total(santa_clara_county):
    inc = Incident("fall")
    for k, v in [("patient.age", 40), ("trauma.mechanism", "fall"), ("vitals.gcs_total", 6)]:
        said(inc, k, v)
    assert "Trauma alert: not following commands (GCS 6)" in texts(builder().build(inc), "injuries")


def test_every_criterion_has_spoken_wording_and_gaps_are_startup_problems():
    cfg = HandoffConfig.from_config()
    scales, trends = default_scales(), TrendRules.from_config()
    ids = ChecklistEngine.from_config(default_counties()).ids()
    assert cfg.problems(default_vocabulary(), scales, LINE_KINDS, ids, trends) == []
    broken = copy.deepcopy(cfg.criteria_say)
    del broken["trauma_605"]["N.4"]
    broken["trauma_605"]["ZZ"] = ["nothing"]
    broken["field_triage"]["red.1"] = ["{vitals.nope}"]
    bad = HandoffConfig(cfg.formats, cfg.select, cfg.default, cfg.words, cfg.value_text, cfg.score_text,
                        cfg.time_format, broken)
    joined = " | ".join(bad.problems(default_vocabulary(), scales, LINE_KINDS, ids, trends))
    for needle in ("no wording for criterion 'N.4'", "unknown criterion 'ZZ'", "unknown key 'vitals.nope'"):
        assert needle in joined, needle


def test_a_trend_key_without_a_change_rule_is_a_startup_problem():
    spec = {"kind": "trends", "keys": ["vitals.hr", "vitals.gcs_total"], "template": "{label} {direction}, {series}",
            "directions": {"up": "rising", "down": "falling", "flat": "changing"}}
    errs = LINE_KINDS["trends"].problems(spec, default_vocabulary(), default_scales(), HandoffConfig.from_config(),
                                         trends=TrendRules.from_config())
    assert errs == ["vitals.gcs_total has no change rule in config/trends.yaml"]


# ---------- no score bookkeeping ----------
def test_score_bookkeeping_is_not_read_aloud(santa_clara_county):
    r = builder().build(rollover())
    assert not any("NEWS2" in t for t in texts(r, "signs"))
    assert "incomplete" not in r["text"] and "undecided" not in r["text"] and "RCP 2017" not in r["text"]


def test_a_complete_score_is_one_short_line(santa_clara_county):
    inc = rollover()
    for k, v in [("vitals.on_oxygen", False), ("vitals.consciousness", "V"), ("vitals.temp", 36.5)]:
        said(inc, k, v)
    news2 = [t for t in texts(builder().build(inc), "signs") if t.startswith("NEWS2")]
    assert len(news2) == 1 and news2[0].endswith("high risk") and "(" not in news2[0]


def test_an_incomplete_news2_is_not_listed_as_a_gap_either(santa_clara_county):
    inc = Incident("fever")
    for k, v in [("infection.suspected", "pneumonia"), ("vitals.hr", 110)]:
        said(inc, k, v)
    r = builder().build(inc)
    assert "sepsis" in r["open_checklists"]
    assert "NEWS2 complete" not in [g["label"] for g in r["not_yet_known"]]
    assert "Temperature" in [g["label"] for g in r["not_yet_known"]] or "Temperature: not yet known" in r["text"]


# ---------- trends ----------
def test_a_change_below_the_trend_rule_is_not_read(santa_clara_county):
    r = builder().build(rollover())                       # HR 132 -> 142: 10/min, the rule is 20
    assert not [ln for ln in all_lines(r) if ln["kind"] == "trend"]


def test_a_meaningful_trend_is_said_without_seconds(santa_clara_county):
    inc = Incident("fall")
    said(inc, "vitals.hr", 118)
    said(inc, "vitals.hr", 142)
    lines = [ln for ln in all_lines(builder().build(inc)) if ln["kind"] == "trend"]
    assert [ln["text"] for ln in lines] == ["HR rising, 118 → 142"]
    assert len(lines[0]["fact_ids"]) == 2 and lines[0]["sources"][0]["time"]      # when is kept in the JSON


def test_a_long_trend_keeps_first_extreme_and_latest(santa_clara_county):
    inc = Incident("fall")
    for v in (120, 100, 84, 90):
        said(inc, "vitals.sbp", v)
    trend = next(ln["text"] for ln in all_lines(builder().build(inc)) if ln["kind"] == "trend")
    assert trend == "SBP falling, 120 → 84 → 90"


def test_a_key_without_a_change_rule_has_no_trend_line(santa_clara_county):
    inc = Incident("fall")
    said(inc, "vitals.gcs_total", 14)
    said(inc, "vitals.gcs_total", 9)
    assert not [ln for ln in all_lines(builder().build(inc)) if ln["kind"] == "trend"]


# ---------- sections and repetition ----------
def test_empty_sections_are_left_out(santa_clara_county):
    r = builder().build(rollover())
    ids = [s["id"] for s in r["sections"]]
    assert "before_arrival" not in ids and "other" not in ids and all(s["lines"] for s in r["sections"])
    assert "Before arrival" not in r["text"] and "Other" not in r["text"]
    assert "treatment" in ids                              # "none recorded" is something to say
    inc = rollover()
    said(inc, "scene.notes", "car on its roof")
    assert texts(builder().build(inc), "other") == ["Scene: car on its roof"]


def test_complaint_and_mechanism_are_said_once(santa_clara_county):
    inc = rollover()                                       # complaint set, mechanism not said
    r = builder().build(inc)
    assert "Chief complaint: rollover with ejection" in texts(r, "opening")
    assert texts(r, "mechanism") == ["Mechanism of injury: not yet known"]
    said(inc, "trauma.mechanism", "Rollover with ejection")
    r = builder().build(inc)
    assert not any(t.startswith("Chief complaint") for t in texts(r, "opening"))
    assert texts(r, "mechanism") == ["Rollover with ejection"] and r["text"].lower().count("rollover") == 1
    medical = builder().build(inc, "medical")
    assert medical["text"].lower().count("rollover") == 1
    said(inc, "trauma.mechanism", "rollover at highway speed")                       # different: both said
    assert "Chief complaint: rollover with ejection" in texts(builder().build(inc), "opening")


# ---------- not obtained: the report ----------
def test_a_marked_required_line_reads_unable_to_obtain(santa_clara_county):
    inc = rollover()
    unobtainable.mark(inc, "allergies", True)
    r = builder().build(inc)
    line = next(ln for ln in section(r, "history")["lines"] if ln["text"].startswith("Allergies"))
    assert line["text"] == "Allergies: unable to obtain" and line["status"] == "not_obtained"
    assert r["not_obtained"] == [{"key": "allergies", "label": "Allergies", "inline": True}]
    assert "Unable to obtain:" not in r["text"]                                     # said once, in its place
    assert "Allergies: unable to obtain" in r["text"]


def test_a_marked_gap_moves_from_not_yet_known_to_not_obtained(santa_clara_county):
    inc = rollover()
    r = builder().build(inc)
    assert [g["key"] for g in r["not_yet_known"]] == ["transport.destination"]
    assert all({"key", "label"} <= set(g) for g in r["not_yet_known"])
    unobtainable.mark(inc, "transport.destination", True)
    r = builder().build(inc)
    assert r["not_yet_known"] == []
    assert r["not_obtained"] == [{"key": "transport.destination", "label": "Destination", "inline": False}]
    assert "Unable to obtain: Destination." in r["text"]


def test_a_confirmed_fact_wins_over_a_mark(santa_clara_county):
    inc = rollover()
    unobtainable.mark(inc, "allergies", True)
    said(inc, "allergies", ["penicillin"])
    r = builder().build(inc)
    assert "Allergies: penicillin" in texts(r, "history") and r["not_obtained"] == []
    assert inc.snapshot()["incident"]["not_obtained"] == []
    with pytest.raises(unobtainable.NotObtainedRefused):
        unobtainable.mark(inc, "allergies", True)


def test_marks_are_refused_after_the_call_ended():
    inc = Incident("fall")
    inc.ended_at = inc.started
    with pytest.raises(IncidentEnded):
        unobtainable.mark(inc, "allergies", True)


def test_needs_attention_stops_asking_for_a_marked_item(santa_clara_county):
    inc = rollover()
    before = inc.snapshot()["needs_attention"]
    keys = lambda na: {x["key"] for x in na["missing"] + na["unknown"]}                  # noqa: E731
    assert {"allergies", "transport.destination"} <= keys(before)
    unobtainable.mark(inc, "allergies", True)
    unobtainable.mark(inc, "transport.destination", True)
    snap = inc.snapshot()
    assert "allergies" not in keys(snap["needs_attention"])
    assert "transport.destination" not in keys(snap["needs_attention"])
    assert snap["incident"]["not_obtained"] == ["allergies", "transport.destination"]


# ---------- not obtained: the API ----------
def test_api_marks_unmarks_and_refuses():
    c, ctx = make_client()
    c.post("/api/incident", json={"dispatch": "fall"})
    on = c.post("/api/handoff/not-obtained", json={"key": "allergies", "on": True})
    assert on.status_code == 200
    body = on.json()
    assert {"incident", "as_of", "text", "format", "formats", "sections", "not_yet_known", "not_yet_confirmed",
            "not_obtained"} <= set(body)
    assert "Allergies: unable to obtain" in body["text"]
    assert [x["key"] for x in body["not_obtained"]] == ["allergies"]
    state = c.get("/api/state").json()
    assert state["incident"]["not_obtained"] == ["allergies"]
    assert "allergies" not in {x["key"] for x in state["needs_attention"]["unknown"] + state["needs_attention"]["missing"]}
    assert ctx.incident.audit_log[-1] | {"at": None} == {"at": None, "action": "not_obtained", "actor": "medic",
                                                         "key": "allergies", "on": True}
    off = c.post("/api/handoff/not-obtained", json={"key": "allergies", "on": False}).json()
    assert off["not_obtained"] == [] and "Allergies: not yet known" in off["text"]
    assert ctx.incident.audit_log[-1]["on"] is False
    # a checklist item's alternatives are accepted as one key
    assert c.post("/api/handoff/not-obtained",
                  json={"key": "vitals.gcs_total|vitals.gcs_motor", "on": True}).status_code == 200
    assert c.post("/api/handoff/not-obtained", json={"key": "vitals.nope", "on": True}).status_code == 422
    assert c.post("/api/handoff/not-obtained", json={"key": "@news2", "on": True}).status_code == 422
    fact = c.post("/api/facts", json=[{"key": "vitals.hr", "value": 118, **MONITOR}]).json()[0]
    c.post(f"/api/facts/{fact['id']}/confirm")
    assert c.post("/api/handoff/not-obtained", json={"key": "vitals.hr", "on": True}).status_code == 409
    c.post("/api/incident/end")
    assert c.post("/api/handoff/not-obtained", json={"key": "meds.list", "on": True}).status_code == 409


def test_marks_are_persisted_with_the_call(tmp_path):
    _, ctx = make_client()
    unobtainable.mark(ctx.incident, "allergies", True)
    restored = decode_call(ctx, encode_call(ctx.roster, ctx.relay))
    inc = next(i for i in restored.roster.incidents() if i.id == ctx.incident.id)
    assert inc.not_obtained == ["allergies"]
    assert inc.audit_log[-1]["action"] == "not_obtained"
    options = dict(data_dir=tmp_path / "data", state_key_file=tmp_path / "private" / "key", persistence=True)
    _, first = make_client(**options)
    unobtainable.mark(first.incident, "meds.list", True)
    first.persist()
    _, again = make_client(**options)
    assert again.incident.not_obtained == ["meds.list"]
