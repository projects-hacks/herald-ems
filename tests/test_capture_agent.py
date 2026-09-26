import asyncio

import pytest

from fakes import FakeVision, make_client, tiny_normalizer
from herald.core.schema import FactIn
from test_capture_gate import frame


def setup(tmp_path, facts):
    vision = FakeVision(facts=facts)
    client, ctx = make_client(vision=vision, normalizer=tiny_normalizer(), data_dir=tmp_path,
                              capture_source="browser")
    # Spy redaction avoids depending on a detector's behavior on synthetic non-face fixtures.
    ctx.frame_reader.store.blur = lambda raw: b"redacted evidence"
    return client, ctx


def run_frame(client, ctx, *, monitor=False, manual=False):
    async def run():
        agent = ctx.capture_agent
        now = [100.0]; agent.clock = lambda: now[0]
        if manual: agent.manual("monitor" if monitor else "pill_bottle")
        agent.receive(frame(now[0]))
        if monitor and not manual:
            now[0] += 1
            agent.receive(frame(now[0]))
        await agent.step()
        if agent.read_task: await agent.read_task
    asyncio.run(run())


def test_monitor_http_controls_device_reading_facts_and_trace_contract(tmp_path):
    """A monitor-watch reading is the monitor's own measurement: recorded confirmed (config/confirmation.yaml
    `monitor_readings`), attributed to the device, with its evidence (frame, ROI, stored still) kept."""
    client, ctx = setup(tmp_path, [FactIn(key="vitals.hr", value=95)])
    assert client.get("/api/capture/status").json()["sees"] == "off"
    assert client.post("/api/capture/auto", json={"on": True}).status_code == 200
    client.post("/api/capture/roi", json={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    run_frame(client, ctx, monitor=True)
    state = client.get("/api/state").json()
    fact = state["facts"]["vitals.hr"]
    assert fact["status"] == "confirmed" and fact["captured_by"] == "camera"
    assert fact["role"] == "device" and fact["speaker"] == "monitor"
    assert fact["provenance"]["trigger"] == "monitor_changed"
    assert fact["provenance"]["frame_id"] and fact["provenance"]["crop"] == [0, 0, 1, 1]
    assert fact["provenance"]["photo_id"] and not fact["provenance"]["hold_reason"]
    assert state["capture_groups"] == []           # nothing for the medic to confirm
    assert state["capture"]["counts"] == {"frames": 2, "gated": 2, "captured": 1, "stored": 1}
    trace = state["transcripts"][-1]
    assert trace["trigger"] == "monitor_changed" and trace["frame_id"]
    assert client.get(f"/api/photo/{trace['photo_id']}").content == b"redacted evidence"


@pytest.mark.parametrize("label,expected", [("ondansetron", "mismatch"), ("naloxone", "match")])
def test_label_verification_preserves_spoken_dose_and_never_adds_home_meds(tmp_path, label, expected):
    client, ctx = setup(tmp_path, [FactIn(key="meds.list", value=[label])])
    client.post("/api/capture/auto", json={"on": True})
    dose = client.post("/api/facts", json=[{"key": "meds.given", "value": {"drug": "Narcan", "dose": .4, "unit": "mg", "by": "crew"}, "confidence": 1}]).json()[0]
    assert dose["status"] == "unconfirmed"  # hold exists before any asynchronous vision work or relay
    run_frame(client, ctx)
    state = client.get("/api/state").json()
    fact = state["facts"]["meds.given"]
    assert fact["value"] == dose["value"]
    assert fact["verify"]["status"] == expected
    assert fact["status"] == "unconfirmed"
    assert "meds.list" not in state["facts"]
    if expected == "mismatch":
        assert "ondansetron" in fact["provenance"]["hold_reason"]
        assert client.post(f"/api/facts/{fact['id']}/confirm").status_code == 409
        kept = client.post(f"/api/capture/verify/{fact['id']}", json={"action": "keep"}).json()
        assert kept["value"] == dose["value"] and kept["status"] == "confirmed"
        assert kept["verify"]["resolution"] == "kept"


def test_off_no_calls_manual_works_and_empty_result_is_not_stored(tmp_path):
    client, ctx = setup(tmp_path, [])
    run_frame(client, ctx)
    assert client.get("/api/capture/status").json()["counts"]["captured"] == 0
    assert client.post("/api/capture/now", json={"mode": "monitor"}).status_code == 202
    run_frame(client, ctx)
    assert ctx.capture_agent.status()["counts"]["captured"] == 1
    assert not list(tmp_path.rglob("*.jpg"))


def test_unchanged_monitor_values_do_not_add_duplicates(tmp_path):
    client, ctx = setup(tmp_path, [FactIn(key="vitals.hr", value=95)])
    run_frame(client, ctx, monitor=True, manual=True)
    before = len(ctx.incident.facts)
    ctx.capture_agent.last_input = float("-inf")
    run_frame(client, ctx, monitor=True, manual=True)
    assert len(ctx.incident.facts) == before
    assert ctx.capture_agent.status()["last"]["reason"] == "unchanged"   # counted, not written into the record
    assert all(t.get("reason") != "unchanged" for t in ctx.incident.transcripts)


def test_bad_roi_and_frames_and_patient_change(tmp_path):
    client, ctx = setup(tmp_path, [])
    assert client.post("/api/capture/roi", json={"x0": .7, "y0": 0, "x1": .1, "y1": 1}).status_code == 422
    client.post("/api/capture/auto", json={"on": True})
    with client.websocket_connect("/ws/frames") as ws:
        ws.send_bytes(b"not jpeg")
        assert ws.receive_json()["accepted"] is False
    assert not ctx.capture_agent.auto
    client.post("/api/capture/roi", json={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    client.post("/api/incident", json={"dispatch": "new patient", "disposition": "transported"})
    status = client.get("/api/capture/status").json()
    assert status["roi"] is None and status["auto"] is False


def test_every_frame_gets_a_reply_even_when_early(tmp_path):
    """The page waits for a reply before sending again; a frame dropped in silence looked like a dead camera."""
    client, ctx = setup(tmp_path, [])
    client.post("/api/capture/auto", json={"on": True})
    with client.websocket_connect("/ws/frames") as ws:
        ws.send_bytes(b"not jpeg")
        assert ws.receive_json()["accepted"] is False
        ws.send_bytes(b"not jpeg")                  # well inside one second of the first: over the input rate
        assert ws.receive_json() == {"accepted": False, "gate": None, "throttled": True}


def test_stale_controls_cannot_change_new_patient(tmp_path):
    client, ctx = setup(tmp_path, [])
    old = ctx.incident.id
    client.post("/api/incident", json={"dispatch": "new patient", "disposition": "transported"})
    for path, body in [("auto", {"on": True}), ("now", {}), ("roi", {"x0": 0, "y0": 0, "x1": 1, "y1": 1})]:
        assert client.post(f"/api/capture/{path}", json={**body, "incident_id": old}).status_code == 409
    assert client.delete("/api/capture/roi", params={"incident_id": old}).status_code == 409
    assert not ctx.capture_agent.auto and not ctx.capture_agent.pending


def test_edit_is_explicit_and_original_evidence_is_preserved(tmp_path):
    client, ctx = setup(tmp_path, [FactIn(key="meds.list", value=["ondansetron"])])
    client.post("/api/capture/auto", json={"on": True})
    value = {"drug": "Narcan", "dose": .4, "unit": "mg", "route": "IV", "by": "crew"}
    dose = client.post("/api/facts", json=[{"key": "meds.given", "value": value}]).json()[0]
    run_frame(client, ctx)
    url = f"/api/capture/verify/{dose['id']}"
    assert client.post(url, json={"action": "edit"}).status_code == 422
    edited = client.post(url, json={"action": "edit", "value": {**value, "drug": "ondansetron"}}).json()
    assert edited["id"] != dose["id"] and edited["status"] == "confirmed"
    assert edited["value"] == {**value, "drug": "ondansetron"}
    original = next(f for f in ctx.incident.facts if f.id == dose["id"])
    assert original.status.value == "rejected" and original.verify.resolution == "edited"
    assert original.value == dose["value"] and original.verify.photo_id
    assert client.post(url, json={"action": "keep"}).status_code == 409


def test_a_newer_camera_link_takes_over_and_the_old_one_is_told_why(tmp_path):
    """A link cut without a close is never reported; refusing new links behind it kept the camera "reconnecting"."""
    from starlette.websockets import WebSocketDisconnect
    client, ctx = setup(tmp_path, [])
    client.post("/api/capture/auto", json={"on": True})
    with client.websocket_connect("/ws/frames") as old:
        with client.websocket_connect("/ws/frames") as new:
            with pytest.raises(WebSocketDisconnect) as closed:
                old.receive_json()
            assert closed.value.code == 4001
            new.send_bytes(b"not jpeg")
            assert new.receive_json()["accepted"] is False       # the new link is the one being answered
            assert ctx.extra["frame_socket"] is not None
