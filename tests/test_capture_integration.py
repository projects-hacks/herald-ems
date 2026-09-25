"""Cross-branch guards: roster changes, camera queues and explicit label review."""
from fakes import make_client
from herald.core.schema import FactIn, Verification


def test_patient_switch_resets_agent_and_keeps_scoped_capture_listeners():
    client, ctx = make_client()
    original = ctx.incident
    scoped = client.app.state.capture.for_incident()
    assert ctx.capture_agent in scoped.listeners
    assert client.post("/api/capture/auto", json={"on": True}).status_code == 200
    assert client.post("/api/capture/roi", json={"x0": .1, "y0": .1, "x1": .9, "y1": .9}).status_code == 200
    client.post("/api/capture/now", json={"mode": "monitor"})
    state = client.post("/api/patients", json={"label": "Patient two"}).json()
    assert state["active_patient"] != original.id
    assert not state["capture"]["auto"] and state["capture"]["roi"] is None
    assert state["capture"]["pending"] == 0
    assert client.post("/api/capture/auto", json={"on": True, "incident_id": original.id}).status_code == 409
    scoped.ingest_batch([FactIn(key="vitals.hr", value=95)])
    assert original.latest("vitals.hr") and not ctx.incident.facts


def test_general_correction_cannot_bypass_label_mismatch():
    client, ctx = make_client()
    fact = ctx.incident.ingest(FactIn(key="meds.given", value={"drug": "naloxone", "dose": .4, "unit": "mg"}))
    ctx.incident.apply_verification(fact.id, Verification(status="mismatch", label_drug="ondansetron"), pending_reason="")
    url = f"/api/facts/{fact.id}"
    assert client.post(url + "/confirm").status_code == 409
    assert client.post(url + "/correct", json={"value": fact.value}).status_code == 409
    assert fact.status.value == "unconfirmed"
    assert client.post(f"/api/capture/verify/{fact.id}", json={"action": "keep"}).status_code == 200
    assert fact.status.value == "confirmed" and fact.verify.resolution == "kept"
