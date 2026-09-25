import asyncio

import pytest
from fastapi.testclient import TestClient
from fakes import make_client
from herald.core.incident import IncidentEnded
from herald.core.schema import CapturedBy, FactIn, Role
from ed_receiver.app import app, INCIDENTS, LINK


def test_stale_patient_capture_rejected_and_late_work_never_reaches_the_new_patient():
    # A new incident ends the previous call (its media is deleted; nothing more may be written to it). Work still
    # in flight for that call is refused, and it must never land on the new patient.
    client, ctx = make_client()
    original = ctx.incident
    scoped = client.app.state.capture.for_incident()
    client.post("/api/incident", json={"dispatch": "fall"})
    headers = {"X-Herald-Patient": original.id}
    assert client.post("/api/facts", headers=headers, json=[]).status_code == 409
    assert client.post("/api/transcript", headers=headers, json={"text": "test", "use_llm": False}).status_code == 409
    with pytest.raises(IncidentEnded):
        scoped.ingest_batch([FactIn(key="vitals.hr", value=95)])
    assert original.latest("vitals.hr") is None and original.ended_at is not None
    assert ctx.incident.latest("vitals.hr") is None
    assert ctx.incident.dispatch == "fall"
    assert client.get("/classic/capture.html").status_code == 200


def test_scoped_text_capture_cannot_append_after_call_end():
    client, ctx = make_client()
    original = ctx.incident
    scoped = client.app.state.capture.for_incident()
    client.post("/api/incident", json={"dispatch": "fall"})

    with pytest.raises(IncidentEnded):
        asyncio.run(scoped.text("late words", CapturedBy.medic, Role.medic, "medic", None, use_model=False))

    assert original.transcripts == []
    assert ctx.incident.transcripts == []


def test_ed_report_uses_received_facts_and_preserves_event_history():
    INCIDENTS.clear(); LINK["last_contact_at"] = None
    try:
        client = TestClient(app)
        assert client.get("/api/handoff/missing").status_code == 404
        assert "procedures.done" in client.get("/api/meta").json()["keys"]
        display = client.get("/api/meta").json()["display"]
        assert display["critical_px"] == 48 and display["body_px"] == 32 and display["highlight_ms"] == 2000
        packet = {"i": "test-patient", "q": 1, "tier": "full", "f": {"patient.age": 68, "new.unknown": "keep visible"},
                  "tl": [{"k": "meds.given", "v": {"drug": "naloxone", "dose": .4, "unit": "mg"}, "t": "2026-09-25T01:00:00+00:00"},
                         {"k": "meds.given", "v": {"drug": "aspirin", "dose": 324, "unit": "mg"}, "t": "2026-09-25T01:01:00+00:00"}]}
        assert client.post("/ingest", json=packet).status_code == 200
        response = client.get("/api/handoff/test-patient")
        assert response.status_code == 200
        report = response.json()
        assert report["incident"]["id"] == "test-patient"
        assert report["county"]["id"] == "generic"
        assert "naloxone" in report["text"] and "aspirin" in report["text"]
        assert not report["not_yet_confirmed"] and "Received confirmed" in report["scope"]
        state = client.get("/state").json()
        assert state["last_contact_at"] and "new.unknown" in state["incidents"]["test-patient"]["fields"]
        assert client.get("/api/handoff/test-patient?format=invalid").status_code == 400
    finally:
        INCIDENTS.clear(); LINK["last_contact_at"] = None
