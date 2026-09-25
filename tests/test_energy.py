"""E3: GPU energy attributed per inference request (power x its own elapsed time), not a since-start total."""
from __future__ import annotations

import time

import pytest

from fakes import make_client
from herald.telemetry import Telemetry, tracking


def test_track_attributes_only_the_energy_sampled_during_the_call():
    t = Telemetry()
    t.energy_j = 10.0                        # energy accumulated before this request (e.g. idle sampling)
    with t.track("text"):
        t.energy_j += 5.0                    # what the sampler would have added while this call was in flight
        time.sleep(0.01)
    assert t.energy_j_attributed == 5.0      # only the delta during the call, not the pre-existing 10 J
    assert len(t.request_energy) == 1
    row = t.request_energy[0]
    assert row["kind"] == "text" and row["energy_j"] == 5.0 and row["duration_s"] > 0
    assert row["watts_avg"] == pytest.approx(5.0 / row["duration_s"], rel=0.05)


def test_track_never_attributes_negative_energy():
    t = Telemetry()
    t.energy_j = 20.0
    with t.track("stt"):
        t.energy_j = 5.0                     # a sampler reset/restart mid-call: never a negative delta
    assert t.request_energy[-1]["energy_j"] == 0.0
    assert t.energy_j_attributed == 0.0


def test_request_energy_log_is_bounded_but_the_running_total_is_not():
    t = Telemetry()
    for _ in range(250):
        with t.track("text"):
            t.energy_j += 1.0
    assert len(t.request_energy) == 200      # deque(maxlen=200)
    assert t.energy_j_attributed == 250.0


def test_snapshot_reports_attributed_energy_separately_from_the_since_start_total():
    t = Telemetry()
    t.energy_j = 3600 * 50                   # 50 Wh since start (includes idle time)
    with t.track("text"):
        t.energy_j += 3600 * 2               # 2 Wh actually spent on this one request
    s = t.snapshot(model=None)
    assert s["energy_wh"] == 52.0                                   # unchanged: the whole-process total
    assert s["requests"]["attributed_energy_wh"] == 2.0             # the defensible, per-request number
    assert s["requests"]["count"] == 1
    assert s["requests"]["recent"][0]["kind"] == "text"


def test_tracking_helper_falls_back_to_a_no_op_for_a_recorder_without_track():
    class MinimalRecorder:
        def record_llm(self, usage, kind="text"):
            pass

        def record_stt(self, audio_seconds):
            pass

    with tracking(MinimalRecorder(), "text"):
        pass                                  # must not raise
    with tracking(None, "text"):
        pass                                  # must not raise


def test_telemetry_endpoint_reports_attributed_energy_and_local_bytes():
    c, ctx = make_client()
    with ctx.telemetry.track("text"):
        ctx.telemetry.energy_j += 1.0
    r = c.get("/api/telemetry")
    assert r.status_code == 200
    body = r.json()
    assert body["requests"]["count"] == 1
    assert body["requests"]["attributed_energy_wh"] == pytest.approx(1.0 / 3600.0, abs=1e-6)
    assert "local_bytes" in body and "local_bytes_by_patient" in body
    assert body["local_bytes_by_patient"][ctx.incident.id] == body["local_bytes"]
