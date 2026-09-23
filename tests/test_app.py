"""HTTP/WebSocket behaviour the screens rely on: heartbeat, monitor-panel and failed-photo trace
entries, all-or-nothing structured facts, and the /classic/ safety-net page."""
import os

os.environ["HERALD_WARM_STT"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from ed_receiver import app as ed_mod  # noqa: E402
from herald import app as app_mod  # noqa: E402
from herald import llm, vision  # noqa: E402

MONITOR = {"captured_by": "device", "role": "device", "speaker": "monitor", "confidence": 0.99,
           "provenance": {"extractor": "manual"}}


def _client(monkeypatch):
    monkeypatch.setattr(app_mod.RELAY, "ed_url", None)
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(llm, "model_name", lambda: None)
    c = TestClient(app_mod.app)
    c.post("/api/incident", json={"dispatch": "possible stroke"})
    return c


def test_ws_heartbeat(monkeypatch):
    c = _client(monkeypatch)
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_text("ping")
        msg = ws.receive_json()
        assert msg["type"] == "pong" and msg["t"]
        ws.send_text("something else")      # ignored, no reply
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_monitor_facts_get_one_trace_entry(monkeypatch):
    c = _client(monkeypatch)
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


def test_structured_facts_are_all_or_nothing(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR},
                                   {"key": "vitals.nope", "value": 1, **MONITOR}])
    assert r.status_code == 400
    s = c.get("/api/state").json()
    assert not s["facts"] and s["transcripts"] == []


def test_failed_photo_leaves_a_trace_entry(monkeypatch):
    c = _client(monkeypatch)

    def boom(raw, mode, photo_id):
        raise RuntimeError("vision model unavailable")
    monkeypatch.setattr(vision, "read_photo", boom)
    r = c.post("/api/photo", files={"file": ("x.jpg", b"\xff\xd8fake", "image/jpeg")}, data={"mode": "form"})
    assert r.status_code == 503
    e = c.get("/api/state").json()["transcripts"][-1]
    assert e["captured_by"] == "camera" and e["fact_ids"] == []
    assert e["trace"]["model"]["status"] == "error" and "unavailable" in e["trace"]["model"]["error"]
    assert e["trace"]["heard"]["photo_id"] == e["photo_id"]
    assert c.get(f"/api/photo/{e['photo_id']}").status_code == 200   # the photo is kept for retry


def test_classic_page_is_served_with_relative_assets(monkeypatch):
    c = _client(monkeypatch)
    page = c.get("/classic/")
    assert page.status_code == 200 and 'src="app.js"' in page.text
    assert c.get("/classic/app.js").status_code == 200
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
