"""B7: a shared device token gates mutating /api/* requests when the deployment configures one."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ed_receiver import app as ed_mod
from fakes import make_client


def test_token_disabled_by_default_every_mutating_call_still_works():
    c, _ = make_client()
    r = c.post("/api/patients", json={"label": "Patient 2"})
    assert r.status_code == 200


def test_configured_token_blocks_a_mutating_call_with_no_or_wrong_token():
    c, _ = make_client(device_token="secret-123")
    r = c.post("/api/patients", json={"label": "Patient 2"})
    assert r.status_code == 401
    assert "device token" in r.json()["detail"]
    r = c.post("/api/patients", json={"label": "Patient 2"}, headers={"X-Herald-Token": "wrong"})
    assert r.status_code == 401


def test_configured_token_admits_a_mutating_call_with_the_right_token():
    c, _ = make_client(device_token="secret-123")
    r = c.post("/api/patients", json={"label": "Patient 2"}, headers={"X-Herald-Token": "secret-123"})
    assert r.status_code == 200


def test_configured_token_never_gates_reads_or_the_websocket():
    c, _ = make_client(device_token="secret-123")
    assert c.get("/api/state").status_code == 200
    assert c.get("/api/health").status_code == 200
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state"


def test_ed_receiver_ingest_and_reset_are_open_when_no_token_is_configured(monkeypatch):
    monkeypatch.delenv("ED_RECEIVER_TOKEN", raising=False)
    c = TestClient(ed_mod.app)
    assert c.post("/reset").status_code == 200
    assert c.post("/ingest", json={"i": "inc-token-1", "q": 1, "tier": "critical", "f": {}, "x": 0}).status_code == 200


def test_ed_receiver_ingest_and_reset_require_the_configured_token(monkeypatch):
    monkeypatch.setenv("ED_RECEIVER_TOKEN", "ed-secret")
    c = TestClient(ed_mod.app)
    denied = c.post("/reset")
    assert denied.status_code == 401 and "device token" in denied.json()["detail"]
    r = c.post("/reset", headers={"X-Herald-Token": "ed-secret"})
    assert r.status_code == 200
    ingest_denied = c.post("/ingest", json={"i": "inc-token-2", "q": 1, "tier": "critical", "f": {}, "x": 0},
                           headers={"X-Herald-Token": "wrong"})
    assert ingest_denied.status_code == 401
    ingest_ok = c.post("/ingest", json={"i": "inc-token-2", "q": 1, "tier": "critical", "f": {}, "x": 0},
                       headers={"X-Herald-Token": "ed-secret"})
    assert ingest_ok.status_code == 200
    # /ping and /state stay open even with a token configured: they carry nothing back to the ambulance.
    assert c.get("/ping").status_code == 200 and c.get("/state").status_code == 200


def test_relay_sends_the_configured_ed_token_on_every_outbound_request():
    from herald.relay import Relay

    async def transport(wire):
        return {"ack": 1}

    relay = Relay(lambda: [], "http://ed.example.org", transport=transport, ed_token="ed-secret")
    assert relay._headers()["X-Herald-Token"] == "ed-secret"
    assert relay._headers({"Content-Type": "application/json"}) == {
        "X-Herald-Token": "ed-secret", "Content-Type": "application/json"}
    no_token_relay = Relay(lambda: [], "http://ed.example.org", transport=transport)
    assert no_token_relay._headers() == {}
