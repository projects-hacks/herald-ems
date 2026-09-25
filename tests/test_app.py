"""HTTP/WebSocket behaviour the screens rely on: heartbeat, monitor-panel and failed-photo trace
entries, all-or-nothing structured facts, and the /classic/ safety-net page."""
from fastapi.testclient import TestClient

from ed_receiver import app as ed_mod
from fakes import FakeVision, make_client

MONITOR = {"captured_by": "device", "role": "device", "speaker": "monitor", "confidence": 0.99,
           "provenance": {"extractor": "manual"}}


def test_ws_heartbeat():
    c, _ = make_client()
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_text("ping")
        msg = ws.receive_json()
        assert msg["type"] == "pong" and msg["t"]
        ws.send_text("something else")      # ignored, no reply
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_monitor_facts_get_one_trace_entry():
    c, _ = make_client()
    r = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR},
                                   {"key": "vitals.hr", "value": 88, **MONITOR}])
    assert r.status_code == 200 and len(r.json()) == 2
    entries = c.get("/api/state").json()["transcripts"]
    assert len(entries) == 1
    e = entries[0]
    assert e["captured_by"] == "device" and e["speaker"] == "monitor"
    assert e["fact_ids"] == [f["id"] for f in r.json()]
    assert [f["key"] for f in e["trace"]["rules"]["facts"]] == ["vitals.sbp", "vitals.hr"]
    assert e["trace"]["rules"]["facts"][0]["extractor"] == "manual"
    assert e["trace"]["model"]["status"] == "off"
    assert "150" in e["trace"]["heard"]["text"] and "88" in e["trace"]["heard"]["text"]


def test_structured_facts_are_all_or_nothing():
    c, _ = make_client()
    r = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR},
                                   {"key": "vitals.nope", "value": 1, **MONITOR}])
    assert r.status_code == 400
    s = c.get("/api/state").json()
    assert not s["facts"] and s["transcripts"] == []


def test_failed_photo_leaves_a_trace_entry(tmp_path):
    c, _ = make_client(vision=FakeVision(fail=True), data_dir=tmp_path)
    r = c.post("/api/photo", files={"file": ("x.jpg", b"\xff\xd8fake", "image/jpeg")}, data={"mode": "form"})
    assert r.status_code == 503
    e = c.get("/api/state").json()["transcripts"][-1]
    assert e["captured_by"] == "camera" and e["fact_ids"] == []
    assert e["trace"]["model"]["status"] == "error" and "unavailable" in e["trace"]["model"]["error"]
    assert e["trace"]["heard"]["photo_id"] == e["photo_id"]
    assert c.get(f"/api/photo/{e['photo_id']}").status_code == 200   # the photo is kept for retry


def test_classic_page_is_served_with_relative_assets():
    c, _ = make_client()
    page = c.get("/classic/")
    assert page.status_code == 200 and 'src="app.js"' in page.text
    assert page.text.index('src="wav.js"') < page.text.index('src="app.js"')    # push-to-talk's WAV encoder, shared
    assert c.get("/classic/app.js").status_code == 200 and c.get("/classic/wav.js").status_code == 200
    assert c.get("/classic/style.css").status_code == 200


def test_ed_receiver_heartbeat_and_last_contact():
    c = TestClient(ed_mod.app)
    c.post("/reset")
    assert c.get("/state").json()["last_contact_at"] is None
    c.get("/ping")
    assert c.get("/state").json()["last_contact_at"]
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_ed_receiver_keeps_the_patient_label_from_relay_packets():
    c = TestClient(ed_mod.app)
    c.post("/reset")
    packet = {"i": "inc-driver", "q": 1, "tier": "critical", "patient": "Driver",
              "f": {"triage.category": "immediate"}, "x": 1}
    assert c.post("/ingest", json=packet).json() == {"ack": 1}
    incident = c.get("/state").json()["incidents"]["inc-driver"]
    assert incident["label"] == "Driver"
    assert incident["fields"]["triage.category"]["v"] == "immediate"


def test_extraction_and_photo_reading_use_their_own_models(tmp_path):
    from fakes import FakeModel
    c, ctx = make_client(FakeModel(name="ems-b"), vision=FakeVision(facts=[]), vision_model=FakeModel(name="omni"),
                         data_dir=tmp_path)
    assert c.get("/api/health").json()["llm_model"] == "ems-b"
    assert c.get("/api/health").json()["vision_model"] == "omni"
    c.post("/api/photo", files={"file": ("x.jpg", b"\xff\xd8fake", "image/jpeg")}, data={"mode": "monitor"})
    assert c.get("/api/state").json()["transcripts"][-1]["trace"]["model"]["name"] == "omni"
