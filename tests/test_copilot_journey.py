"""Selected camera observations become a confirmed, time-stamped journey without retaining video."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from fakes import FakeVision, make_client
from herald.capture.types import CaptureIntent
from herald.core.schema import FactIn
from test_capture_gate import frame


def test_camera_to_confirmed_trend_and_handoff_without_image_retention(tmp_path):
    vision = FakeVision(facts=[FactIn(key="vitals.sbp", value=132)])
    client, ctx = make_client(vision=vision, data_dir=tmp_path)
    ctx.frame_reader.store.config = {**ctx.frame_reader.store.config, "store": "none"}
    intent = CaptureIntent("monitor_changed", "monitor", 6, "monitor", reason="Monitor changed")
    first_time = datetime(2026, 9, 25, 17, 0, tzinfo=timezone.utc)

    def observe(value, seconds):
        vision.facts = [FactIn(key="vitals.sbp", value=value)]
        selected = replace(frame(), ts=first_time.timestamp() + seconds, id=f"frame-{seconds}")
        result = asyncio.run(ctx.frame_reader.read(selected, intent, None, lambda: True))
        return result.facts[0]

    first = observe(132, 0)
    pending = client.get("/api/state").json()
    assert pending["facts"]["vitals.sbp"]["status"] == "unconfirmed"
    assert not pending["changed"]                      # one reading is not a trend
    assert "132" not in client.get("/api/handoff").json()["text"]
    assert client.post("/api/facts/confirm", json={"ids": [first]}).status_code == 200
    second = observe(88, 120)
    # A camera reading raises the change in the cabin before it is tapped (config/trends.yaml
    # unconfirmed_sources), labelled so the screen can ask for the tap -- and it still reaches
    # neither the hospital nor the report until it is confirmed.
    waiting = client.get("/api/state").json()
    pending_trend = next(c for c in waiting["changed"] if c["key"] == "vitals.sbp")
    assert pending_trend["unconfirmed"] and pending_trend["unconfirmed_fact_ids"] == [second]
    assert "confirm the reading" in pending_trend["message"]
    assert "88" not in client.get("/api/handoff").json()["text"]
    assert client.post("/api/facts/confirm", json={"ids": [second]}).status_code == 200
    state = client.get("/api/state").json()
    trend = next(change for change in state["changed"] if change["key"] == "vitals.sbp")
    assert trend["series"] == [132, 88] and trend["significant"]
    assert trend["times"] == [first_time.isoformat(), datetime(2026, 9, 25, 17, 2, tzinfo=timezone.utc).isoformat()]
    assert any(alert["type"] == "significant_change" for alert in state["alerts"])
    report = client.get("/api/handoff").json()
    line = next(line for section in report["sections"] for line in section["lines"] if line["kind"] == "trend")
    assert line["text"] == "SBP falling, 132 → 88"          # spoken handover: no seconds, time kept in sources
    assert line["sources"][0]["frame_id"] == "frame-0"
    assert line["sources"][0]["observed_at"] == first_time.isoformat()
    assert all(source["photo_id"] is None for source in line["sources"])
    assert not list(tmp_path.rglob("*.jpg"))

    # Full relay preserves observed time without sending media; the ED builds its own received-only report.
    from ed_receiver.report import received_report
    from herald.relay.relay import Relay
    relay = Relay(lambda: ctx.incident)
    relay.authorize("Test receiver")
    packet = relay._build_full()
    assert packet["tl"][0]["o"] == first_time.isoformat()
    received = received_report(ctx.incident.id, {"first_at": first_time.isoformat(), "timeline": packet["tl"], "fields": {}})
    line = next(line for section in received["sections"] for line in section["lines"] if line["kind"] == "trend")
    assert line["text"] == "SBP falling, 132 → 88" and line["sources"][0]["observed_at"] == first_time.isoformat()


def test_received_lkw_elapsed_metadata_is_invalidated_on_change_or_withdrawal():
    from fastapi.testclient import TestClient
    from ed_receiver.app import app
    client = TestClient(app)
    client.post("/reset")
    packet = {"i": "clock-test", "q": 1, "tier": "full", "f": {"stroke.lkw": "13:04"},
              "tl": [], "lkw_at": "2026-09-25T13:04:00-07:00", "x": 0}

    def state():
        return client.get("/state").json()["incidents"]["clock-test"]

    assert client.post("/ingest", json=packet).status_code == 200
    assert state()["lkw_at"] == packet["lkw_at"]
    client.post("/ingest", json={"i": "clock-test", "q": 2, "f": {"stroke.lkw": "13:14"}})
    assert state().get("lkw_at") is None
    client.post("/ingest", json={**packet, "q": 3})
    client.post("/ingest", json={"i": "clock-test", "q": 4, "rm": ["stroke.lkw"]})
    assert state().get("lkw_at") is None and "stroke.lkw" not in state()["fields"]


def test_empty_full_sync_clears_previous_received_journey():
    from fastapi.testclient import TestClient
    from ed_receiver.app import app
    client = TestClient(app)
    client.post("/reset")
    client.post("/ingest", json={"i": "history-test", "q": 1, "tier": "full", "tl": [
        {"k": "vitals.hr", "v": 100, "t": "2026-09-25T13:00:00Z", "r": "medic", "s": None}]})
    client.post("/ingest", json={"i": "history-test", "q": 2, "tier": "full", "tl": []})
    assert client.get("/state").json()["incidents"]["history-test"]["timeline"] == []
