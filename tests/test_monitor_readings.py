"""Readings the camera takes from the patient monitor are device readings (owner's decision, 2026-09-26).

They go into the record confirmed, attributed to the monitor, and flow into the trends and the ED update like any
confirmed vital; nothing about them waits in Needs you. The rails that stay: plausibility ranges drop a value, and the
capture agent's jump check (config/capture.yaml `monitor.jump`, herald/capture/sanity.py) holds a reading that moved
implausibly fast, with its reason. Every monitor vital the vocabulary knows is read, EtCO2 included, and the read
cadence follows the speech: frequent in a quiet cabin, backed off while speech is being processed.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import numpy as np
from fakes import FakeVision, make_client, tiny_normalizer
from herald.capture.agent import CaptureAgent
from herald.capture.config import capture_config
from herald.capture.policy import CapturePolicy
from herald.capture.sanity import MonitorJumpCheck
from herald.capture.types import CaptureIntent, CaptureResult, GateResult, ROI
from herald.config import load_yaml
from herald.core.confirmation import ConfirmationPolicy, monitor_auto_confirm, monitor_reading
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Provenance, Role, Status
from herald.core.vocabulary import default_vocabulary
from herald.models import VisionReader
from herald.relay import Relay
from test_capture_gate import frame

CAPTURE = capture_config()
JUMP = CAPTURE["monitor"]["jump"]
T0 = datetime(2026, 9, 26, 2, 0, tzinfo=timezone.utc)


def monitor_fact(key, value, *, at=T0, hold=None, **kw) -> FactIn:
    return FactIn(key=key, value=value, captured_by=CapturedBy.camera, role=Role.device, speaker="monitor",
                  confidence=0.9, provenance=Provenance(extractor="vision:test", frame_id=f"f{at.timestamp():.0f}",
                                                        observed_at=at, hold_reason=hold, auto=True), **kw)


# ---------- the product decision, as config ----------

def test_the_owner_decision_is_config_and_monitor_readings_confirm():
    assert load_yaml("confirmation.yaml")["monitor_readings"]["auto_confirm"] is True
    assert monitor_auto_confirm() is True
    inc = Incident()
    fact = inc.ingest(monitor_fact("vitals.hr", 116))
    assert monitor_reading(fact) and fact.status == Status.confirmed


def test_only_monitor_readings_skip_the_tap():
    """A one-shot photo, another speaker and a held monitor reading all still wait. (A structured device feed is held
    by POST /api/facts itself: herald/api/capture.py `structured`.)"""
    policy = ConfirmationPolicy(default_vocabulary(), 0.8, monitor_confirms=True)
    status = lambda fin: policy.initial_status(fin, None, fin.value)
    assert status(monitor_fact("vitals.hr", 116)) == Status.confirmed
    assert status(monitor_fact("vitals.hr", 116, hold="check the monitor")) == Status.unconfirmed
    assert status(FactIn(key="vitals.hr", value=116, captured_by=CapturedBy.camera, role=Role.photo,
                         confidence=0.99)) == Status.unconfirmed
    assert status(FactIn(key="vitals.hr", value=116, captured_by=CapturedBy.other, confidence=0.99)) == Status.unconfirmed
    off = ConfirmationPolicy(default_vocabulary(), 0.8, monitor_confirms=False)
    assert off.initial_status(monitor_fact("vitals.hr", 116), None, 116) == Status.unconfirmed


def test_a_confirmed_monitor_reading_is_relayed_like_any_confirmed_vital():
    inc = Incident()
    inc.ingest(FactIn(key="triage.category", value="immediate", confidence=0.99))
    inc.ingest(monitor_fact("vitals.spo2", 91))
    sent = []

    async def transport(wire: bytes) -> dict:
        packet = json.loads(wire)
        sent.append(packet)
        return {"ack": packet["q"]}

    relay = Relay(lambda: inc, transport=transport)
    relay.authorize("Regional ED")

    async def drain():
        for _ in range(8):
            if await relay.tick() is None:
                return
    asyncio.run(drain())
    assert any(p["f"].get("vitals.spo2") == 91 for p in sent)


# ---------- the jump check ----------

def check() -> MonitorJumpCheck:
    return MonitorJumpCheck(JUMP, default_vocabulary().label)


def test_jump_config_names_numeric_vocabulary_keys_wider_than_the_look_worth_steps():
    vocab = default_vocabulary()
    look = load_yaml("corroboration.yaml")["plausible_step"]
    assert 0 < JUMP["window_s"] <= 300
    for key, step in JUMP["max_step"].items():
        assert vocab.meta(key)["type"] in ("int", "float"), key
        assert step >= look[key]["max_step"], key     # a misread limit, never tighter than a change worth a look


def test_an_implausible_jump_is_held_with_a_reason_and_a_normal_move_is_not():
    inc = Incident()
    inc.ingest(monitor_fact("vitals.spo2", 94))
    later = T0 + timedelta(seconds=15)
    assert check().reason(monitor_fact("vitals.spo2", 91, at=later), inc.history("vitals.spo2"), later) is None
    why = check().reason(monitor_fact("vitals.spo2", 49, at=later), inc.history("vitals.spo2"), later)
    assert why and "SpO2" in why and "49" in why and "94" in why and "15 s" in why


def test_the_window_bounds_the_check():
    inc = Incident()
    inc.ingest(monitor_fact("vitals.hr", 80))
    later = T0 + timedelta(seconds=JUMP["window_s"] + 1)
    assert check().reason(monitor_fact("vitals.hr", 150, at=later), inc.history("vitals.hr"), later) is None


def test_a_spoken_value_is_not_a_monitor_reference():
    inc = Incident()
    inc.ingest(FactIn(key="vitals.hr", value=80, confidence=0.99))
    assert check().reason(monitor_fact("vitals.hr", 150), inc.history("vitals.hr"), T0) is None


def test_end_to_end_a_misread_is_held_a_real_change_repeats_and_is_recorded(tmp_path):
    client, ctx = setup(tmp_path, [FactIn(key="vitals.spo2", value=94), FactIn(key="vitals.hr", value=116)])
    watch(client)
    read(ctx, 0)
    assert ctx.incident.latest("vitals.spo2").status == Status.confirmed

    ctx.frame_reader.vision.facts = [FactIn(key="vitals.spo2", value=49), FactIn(key="vitals.hr", value=117)]
    read(ctx, 15)                                      # a misread digit: 94 -> 49 in 15 s
    spo2, hr = ctx.incident.latest("vitals.spo2"), ctx.incident.latest("vitals.hr")
    assert hr.status == Status.confirmed
    assert spo2.status == Status.unconfirmed and "94" in spo2.provenance.hold_reason
    state = client.get("/api/state").json()
    group, = state["capture_groups"]                   # the held reading, with its reason, for the medic
    assert group["batch_fact_ids"] == [] and group["individual"][0]["id"] == spo2.id

    ctx.frame_reader.vision.facts = [FactIn(key="vitals.spo2", value=94), FactIn(key="vitals.hr", value=117)]
    read(ctx, 30)                                      # the transient misread does not hold the next good reading
    assert ctx.incident.latest("vitals.spo2").status == Status.confirmed

    ctx.frame_reader.vision.facts = [FactIn(key="vitals.spo2", value=78), FactIn(key="vitals.hr", value=117)]
    read(ctx, 45)                                      # a sudden real fall: held once ...
    assert ctx.incident.latest("vitals.spo2").status == Status.unconfirmed
    read(ctx, 60)                                      # ... and recorded when the next read agrees
    latest = ctx.incident.latest("vitals.spo2")
    assert latest.value == 78 and latest.status == Status.confirmed
    # The medic can still correct any monitor value.
    fixed = client.post(f"/api/facts/{latest.id}/correct", json={"value": 80})
    assert fixed.status_code == 200 and fixed.json()["value"] == 80


def test_a_value_outside_the_plausibility_range_is_not_recorded(tmp_path):
    client, ctx = setup(tmp_path, [FactIn(key="vitals.hr", value=900), FactIn(key="vitals.spo2", value=96)])
    watch(client)
    read(ctx, 0)
    assert ctx.incident.latest("vitals.hr") is None and ctx.incident.latest("vitals.spo2").value == 96


# ---------- EtCO2 ----------

class ScreenModel:
    def __init__(self, facts):
        self.facts = facts

    def available(self):
        return True

    def model_name(self):
        return "fake-vision"

    def chat_json(self, system, user, **kw):
        return {"facts": [dict(f) for f in self.facts]}


def test_the_monitor_prompt_asks_for_etco2_and_the_reader_keeps_it():
    prompt = load_yaml("prompts/vision.yaml")["modes"]["monitor"]
    assert "vitals.etco2" in prompt and "such as EtCO2) is none of these keys" not in prompt
    got = VisionReader(ScreenModel([{"key": "vitals.hr", "value": 116}, {"key": "vitals.etco2", "value": 31},
                                    {"key": "vitals.rr", "value": 20}])).read(b"jpg", "monitor")
    assert {f.key: f.value for f in got} == {"vitals.hr": 116, "vitals.etco2": 31, "vitals.rr": 20}
    dashes = VisionReader(ScreenModel([{"key": "vitals.etco2", "value": 0}])).read(b"jpg", "monitor")
    assert dashes == []                                # a sensor-off 0 is not recorded from a photo


def test_etco2_read_off_the_monitor_is_recorded_and_trended_from_the_monitor(tmp_path):
    client, ctx = setup(tmp_path, [FactIn(key="vitals.etco2", value=31), FactIn(key="vitals.hr", value=116)])
    watch(client)
    read(ctx, 0)
    ctx.frame_reader.vision.facts = [FactIn(key="vitals.etco2", value=27), FactIn(key="vitals.hr", value=126)]
    read(ctx, 15)
    state = client.get("/api/state").json()
    assert state["facts"]["vitals.etco2"]["status"] == "confirmed" and state["facts"]["vitals.etco2"]["value"] == 27
    trend = next(c for c in state["changed"] if c["key"] == "vitals.etco2")
    assert trend["series"] == [31, 27] and trend["confirmed"] == [True, True] and trend["from_monitor"] == [True, True]
    assert trend["significant"] is False               # display only: no change rule reviewed for EtCO2
    hr = next(c for c in state["changed"] if c["key"] == "vitals.hr")
    assert hr["from_monitor"] == [True, True] and not hr["unconfirmed"]


# ---------- cadence ----------

def test_cadence_is_frequent_when_speech_is_idle_and_backs_off_while_it_is_busy():
    m = CAPTURE["monitor"]
    assert m["min_interval_s"] < m["speech_interval_s"] and m["min_interval_s"] < 30
    state = dict(roi=True, usable=True, stable=True, changed=True)
    for speech, interval in ((False, m["min_interval_s"]), (True, m["speech_interval_s"])):
        policy = CapturePolicy(CAPTURE)
        policy.on_tick(0, state)
        intent, = policy.on_tick(1, state)
        policy.captured(intent, 1)
        busy = dict(state, speech_recent=speech)
        assert policy.on_tick(1 + interval - 0.5, busy) == []
        assert policy.on_tick(1 + interval, busy)[0].trigger == "monitor_changed"


def test_an_unchanged_picture_still_gets_a_periodic_refresh_point():
    m = CAPTURE["monitor"]
    policy = CapturePolicy(CAPTURE)
    state = dict(roi=True, usable=True, stable=True, changed=True)
    policy.on_tick(0, state)
    intent, = policy.on_tick(1, state)
    policy.captured(intent, 1)
    still = dict(state, changed=False)
    assert policy.on_tick(1 + m["max_interval_s"] - 0.5, still) == []
    assert policy.on_tick(1 + m["max_interval_s"], still)[0].trigger == "monitor_refresh"


def test_the_agent_tracks_speech_and_the_quiet_window():
    now, busy = [0.0], [True]
    agent = CaptureAgent(CAPTURE, None, incident_id=lambda: "inc", speech_busy=lambda: busy[0], clock=lambda: now[0])
    assert agent.speech_recent(0)
    busy[0] = False
    now[0] = CAPTURE["monitor"]["speech_quiet_s"] - 1
    assert agent.speech_recent(now[0])
    now[0] = CAPTURE["monitor"]["speech_quiet_s"] + 0.1
    assert not agent.speech_recent(now[0])


def test_agent_reads_at_the_quiet_cadence_and_backs_off_while_speech_runs():
    """Frames arrive every second; count the reads the agent starts over two minutes, with and without speech."""
    m = CAPTURE["monitor"]

    def reads_in(seconds, speaking):
        now, calls = [1000.0], []

        async def reader(frame, intent, roi, valid):
            calls.append(now[0])
            return CaptureResult([], None, "read")

        agent = CaptureAgent(CAPTURE, reader, incident_id=lambda: "inc", clock=lambda: now[0],
                             speech_busy=lambda: speaking(now[0]))
        agent.set_auto(True)
        agent.set_roi(ROI(0, 0, 1, 1))
        agent.monitor_gate = SteadyScreen()

        async def run():
            for i in range(seconds):
                now[0] = 1000.0 + i
                agent.receive(frame(now[0]))
                await agent.step()
                if agent.read_task:
                    await agent.read_task
        asyncio.run(run())
        return calls

    quiet = reads_in(120, lambda t: False)
    gaps = [b - a for a, b in zip(quiet, quiet[1:])]
    assert len(quiet) >= 120 // m["min_interval_s"] - 1 and min(gaps) >= m["min_interval_s"]
    # Speech processed for 1 s out of every 8 (an ambient clip cadence): the cadence backs off, reads never start
    # during speech, and they keep coming.
    talking = reads_in(120, lambda t: int(t) % 8 == 0)
    gaps = [b - a for a, b in zip(talking, talking[1:])]
    assert talking and min(gaps) >= m["speech_interval_s"] and all(int(t) % 8 != 0 for t in talking)


def test_a_refresh_read_records_a_repeat_value_but_a_changed_read_does_not(tmp_path):
    client, ctx = setup(tmp_path, [FactIn(key="vitals.hr", value=116)])
    watch(client)
    read(ctx, 0)
    n = len(ctx.incident.history("vitals.hr"))
    read(ctx, 15)                                          # same value, the gate said "changed": a duplicate
    assert len(ctx.incident.history("vitals.hr")) == n
    read(ctx, 30, trigger="monitor_refresh")               # the periodic point: kept
    assert len(ctx.incident.history("vitals.hr")) == n + 1
    assert ctx.incident.latest("vitals.hr").status == Status.confirmed


# ---------- helpers: drive the FrameReader the way the agent does ----------

def setup(tmp_path, facts):
    client, ctx = make_client(vision=FakeVision(facts=facts), normalizer=tiny_normalizer(), data_dir=tmp_path,
                              capture_source="browser")
    ctx.frame_reader.store.blur = lambda raw: b"redacted evidence"
    return client, ctx


def watch(client):
    client.post("/api/capture/auto", json={"on": True})
    client.post("/api/capture/roi", json={"x0": 0, "y0": 0, "x1": 1, "y1": 1})


def read(ctx, t, trigger="monitor_changed"):
    """One monitor read of a frame seen `t` seconds after T0 (the jump check runs on frame time)."""
    ts = T0.timestamp() + t
    intent = CaptureIntent(trigger, "monitor", CAPTURE["buffer_s"], "monitor", reason=CAPTURE["reasons"][trigger])
    return asyncio.run(ctx.frame_reader.read(frame(ts), intent, ROI(0, 0, 1, 1), lambda: True))


class SteadyScreen:
    """The monitor-watch gate over a steady, readable screen whose numbers keep changing: always usable, stable and
    changed, so the cadence alone decides when the agent reads."""

    def __init__(self):
        self.current = np.zeros((4, 4), dtype=np.float32)

    def assess(self, frame, roi=None):
        return GateResult(sharp=100.0, changed=1.0, bright=100.0, passed=True, reason="changed", usable=True)

    def accept(self, frame, roi=None):
        pass

    def clear(self):
        pass
