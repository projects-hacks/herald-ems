"""Trends and the significant_change alert (herald/core/trends.py, herald/core/snapshot.py `_trends`/`_alerts`).

Two paths are covered: the confirmed path (a spoken or confirmed reading), and the unconfirmed camera path, where the
camera reads the patient monitor and the reading is still waiting for the medic's tap. The second path exists so the
copilot can notice a change at the moment it happens. The invariant it must not touch: nothing unverified reaches the
hospital, so the relay and the handoff report are asserted to stay confirmed-only.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from herald.config import load_yaml
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Provenance, Role, Status
from herald.core.trends import TrendRules
from herald.relay import Relay


def said(inc: Incident, key, value, confidence=0.99) -> object:
    """A reading from the medic's own mic: confirmed on arrival."""
    return inc.ingest(FactIn(key=key, value=value, confidence=confidence))


def camera_read(inc: Incident, key, value, *, frame_id="frame_1", trigger="monitor_changed", confidence=0.9):
    """A reading the camera took off the monitor: unconfirmed on arrival (herald/core/confirmation.py)."""
    return inc.ingest(FactIn(key=key, value=value, confidence=confidence, captured_by=CapturedBy.camera,
                             role=Role.photo, speaker="monitor",
                             provenance=Provenance(extractor="vision:test", trigger=trigger, frame_id=frame_id,
                                                   auto=True)))


def trend_for(snapshot, key):
    return next((c for c in snapshot["changed"] if c["key"] == key), None)


def alert_for(snapshot, key):
    return next((a for a in snapshot["alerts"] if a["type"] == "significant_change" and a["key"] == key), None)


# ---------- the rules engine itself ----------

def test_rule_kinds_fire_at_their_boundaries():
    rules = TrendRules.from_config()
    assert rules.significant("vitals.sbp", 140, 160) and not rules.significant("vitals.sbp", 140, 159)
    assert rules.significant("vitals.sbp", 95, 90) and not rules.significant("vitals.sbp", 90, 88)  # falls_to_or_below
    assert rules.significant("vitals.hr", 100, 80) and not rules.significant("vitals.hr", 100, 81)
    assert rules.significant("vitals.spo2", 97, 94) and not rules.significant("vitals.spo2", 97, 95)  # falls_by 3
    assert rules.significant("vitals.spo2", 92, 91) and not rules.significant("vitals.spo2", 91, 90)  # falls_below 92
    assert rules.significant("vitals.rr", 12, 18) and not rules.significant("vitals.rr", 12, 17)
    assert rules.significant("vitals.glucose", 200, 150) and not rules.significant("vitals.glucose", 200, 151)


def test_shipped_config_lists_the_sources_and_the_wording():
    c = load_yaml("trends.yaml")
    assert c["unconfirmed_sources"] == ["camera", "device"]
    for source in c["unconfirmed_sources"]:
        assert source in {m.value for m in CapturedBy}
        assert "confirm" in c["unconfirmed_text"][source]
    rules = TrendRules.from_config()
    assert rules.counts_unconfirmed("camera") and not rules.counts_unconfirmed("medic")
    assert not rules.counts_unconfirmed("other")


def test_sentence_comes_from_config_and_never_recommends():
    rules = TrendRules.from_config()
    sentence = rules.sentence("camera", label="SBP", value=168, previous=140, direction="up", delta=28, unit=None)
    assert sentence == "Camera read SBP 168, up 28 from 140 — confirm the reading"
    with_unit = rules.sentence("camera", label="Systolic BP", value=168, previous=140, direction="up", delta=28,
                               unit="mmHg")
    assert with_unit == "Camera read Systolic BP 168 mmHg, up 28 from 140 — confirm the reading"
    assert not any(word in sentence.lower() for word in (" give ", "should", "recommend", "treat"))
    assert rules.sentence("medic", label="SBP", value=168, previous=140, direction="up", delta=28) is None


# ---------- the confirmed path ----------

def test_confirmed_readings_make_a_trend_and_a_significant_change_alert():
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    said(inc, "vitals.sbp", 168)
    snapshot = inc.snapshot()
    trend = trend_for(snapshot, "vitals.sbp")
    assert trend["series"] == [140, 168] and trend["delta"] == 28 and trend["direction"] == "up"
    assert trend["significant"] and trend["unconfirmed"] is False and trend["unconfirmed_fact_ids"] == []
    assert "message" not in trend
    alert = alert_for(snapshot, "vitals.sbp")
    assert alert["series"] == [140, 168] and alert["unconfirmed"] is False and "message" not in alert


def test_a_small_confirmed_move_is_a_trend_but_not_an_alert():
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    said(inc, "vitals.sbp", 150)
    snapshot = inc.snapshot()
    assert trend_for(snapshot, "vitals.sbp")["significant"] is False
    assert alert_for(snapshot, "vitals.sbp") is None


def test_one_reading_is_not_a_trend():
    inc = Incident()
    said(inc, "vitals.hr", 96)
    assert trend_for(inc.snapshot(), "vitals.hr") is None


def test_a_rejected_reading_leaves_the_trend():
    inc = Incident()
    said(inc, "vitals.hr", 96)
    second = said(inc, "vitals.hr", 130)
    inc.set_status(second.id, Status.rejected)
    assert trend_for(inc.snapshot(), "vitals.hr") is None


def test_an_unconfirmed_spoken_reading_still_makes_no_trend_point():
    """Only the sources config/trends.yaml lists count while unconfirmed. Another speaker's words do not."""
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    heard = inc.ingest(FactIn(key="vitals.sbp", value=168, confidence=0.99, captured_by=CapturedBy.other,
                              role=Role.family, speaker="daughter"))
    assert heard.status == Status.unconfirmed
    assert trend_for(inc.snapshot(), "vitals.sbp") is None


# ---------- the unconfirmed camera path ----------

def test_a_single_camera_read_produces_a_trend_point_and_an_alert_before_any_tap():
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    reading = camera_read(inc, "vitals.sbp", 168)
    assert reading.status == Status.unconfirmed         # nobody has tapped
    snapshot = inc.snapshot()
    trend = trend_for(snapshot, "vitals.sbp")
    assert trend["series"] == [140, 168] and trend["significant"]
    assert trend["unconfirmed"] is True and trend["unconfirmed_fact_ids"] == [reading.id]
    assert trend["message"] == "Camera read Systolic BP 168 mmHg, up 28 from 140 — confirm the reading"
    alert = alert_for(snapshot, "vitals.sbp")
    assert alert is not None and alert["unconfirmed"] is True
    assert alert["unconfirmed_fact_ids"] == [reading.id]
    assert alert["message"] == trend["message"]


def test_two_camera_reads_alone_are_enough_for_a_trend():
    inc = Incident()
    first = camera_read(inc, "vitals.spo2", 96, frame_id="frame_1")
    second = camera_read(inc, "vitals.spo2", 90, frame_id="frame_2")
    trend = trend_for(inc.snapshot(), "vitals.spo2")
    assert trend["series"] == [96, 90] and trend["significant"] and trend["direction"] == "down"
    assert trend["unconfirmed_fact_ids"] == [first.id, second.id]
    assert trend["message"].startswith("Camera read SpO2 90 %")


def test_confirming_the_camera_reading_clears_the_label():
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    reading = camera_read(inc, "vitals.sbp", 168)
    inc.set_status(reading.id, Status.confirmed)
    trend = trend_for(inc.snapshot(), "vitals.sbp")
    assert trend["unconfirmed"] is False and trend["unconfirmed_fact_ids"] == [] and "message" not in trend
    assert alert_for(inc.snapshot(), "vitals.sbp")["unconfirmed"] is False


def test_an_unconfirmed_camera_reading_does_not_move_the_scores():
    """Scores are computed from confirmed facts only; only the trend and the alert see the reading."""
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    camera_read(inc, "vitals.sbp", 168)
    snapshot = inc.snapshot()
    assert snapshot["facts"]["vitals.sbp"]["status"] == "unconfirmed"     # the newest value waits for a tap
    assert inc.values(confirmed_only=True)["vitals.sbp"] == 140           # what every score and the relay read
    assert inc.values(confirmed_only=False)["vitals.sbp"] == 168
    assert trend_for(snapshot, "vitals.sbp")["series"][-1] == 168         # only the trend sees the new reading


# ---------- the invariant: nothing unverified reaches the hospital ----------

def test_an_unconfirmed_camera_reading_never_reaches_a_relay_packet():
    inc = Incident()
    said(inc, "vitals.sbp", 140)
    said(inc, "triage.category", "immediate")
    sent = []

    async def transport(wire: bytes) -> dict:
        packet = json.loads(wire)
        sent.append(packet)
        return {"ack": packet["q"]}

    relay = Relay(lambda: inc, transport=transport)
    relay.authorize("Regional ED")
    asyncio.run(_drain(relay))
    assert any(p["f"].get("vitals.sbp") == 140 for p in sent)

    camera_read(inc, "vitals.sbp", 168)
    before = len(sent)
    asyncio.run(_drain(relay))
    for packet in sent:
        assert packet["f"].get("vitals.sbp") != 168
    assert relay.critical_values(inc)["vitals.sbp"] == 140
    # The alert exists in the cabin at the same moment.
    assert alert_for(inc.snapshot(), "vitals.sbp")["unconfirmed"] is True
    # And once the medic taps, the new value is exactly what the relay then sends.
    reading = inc.history("vitals.sbp")[-1]
    inc.set_status(reading.id, Status.confirmed)
    asyncio.run(_drain(relay))
    assert any(p["f"].get("vitals.sbp") == 168 for p in sent[before:])


async def _drain(relay: Relay, steps: int = 8) -> None:
    for _ in range(steps):
        if await relay.tick() is None:
            return


def test_an_unconfirmed_camera_reading_never_reaches_a_report_line():
    from herald.api.context import build_handoff
    from herald.checklists import ChecklistEngine
    from herald.core.snapshot import default_counties
    from herald.core.vocabulary import default_vocabulary
    from herald.reporting import default_handoff_config
    from herald.scoring import default_scales
    from fakes import test_settings

    inc = Incident("chest pain")
    said(inc, "complaint.chief", "chest pain")
    said(inc, "vitals.sbp", 140)
    camera_read(inc, "vitals.sbp", 168)
    builder = build_handoff(default_handoff_config(), default_vocabulary(), default_scales(),
                            ChecklistEngine.from_config(default_counties()), test_settings())
    report = builder.build(inc)
    lines = [line["text"] for section in report["sections"] for line in section["lines"]]
    assert any("140" in line for line in lines)
    assert not any("168" in line for line in lines)
    assert "168" not in report["text"]
    # The report says so itself, rather than silently dropping the reading.
    assert any(row["label"] == "Systolic BP" for row in report["not_yet_confirmed"])
