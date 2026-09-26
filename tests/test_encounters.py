"""Encounter boundaries preserve the patient record and its own delivery queue."""
import asyncio
import json

import pytest

from fakes import FakeModel, FakeSTT, FakeVision, make_client, test_settings as settings_for_test
from herald.api import build_context
from herald.core.incident import IncidentEnded
from herald.core.schema import FactIn, Status, Verification


def headers(ctx):
    return {"X-Herald-Patient": ctx.incident.id}


def confirmed(ctx, key="vitals.hr", value=116):
    fact = ctx.incident.ingest(FactIn(key=key, value=value))
    return ctx.incident.set_status(fact.id, Status.confirmed)


def test_unknown_patient_can_arrive_transfer_and_finish_independently():
    client, ctx = make_client()
    patient = headers(ctx)
    arrive = client.post("/api/encounters/current/arrive", headers=patient).json()["incident"]
    assert arrive["arrived_at"] and not arrive["transferred_at"] and not arrive["ended_at"]
    assert client.post("/api/encounters/current/arrive", headers=patient).json()["incident"] == arrive
    transfer = client.post("/api/encounters/current/transfer", headers=patient).json()["incident"]
    assert transfer["transferred_at"] and not transfer["ended_at"]
    assert not ctx.incident.values()  # no name, DOB, destination or invented identity required
    finish = client.post("/api/encounters/current/finish", headers=patient)
    assert finish.status_code == 200 and finish.json()["incident"]["ended_at"]
    assert client.post("/api/encounters/current/finish", headers=patient).json()["incident"] == finish.json()["incident"]
    assert client.post("/api/encounters/current/transfer", headers=patient).status_code == 409
    assert client.get("/api/handoff").json()["incident"]["transferred_at"] == transfer["transferred_at"]


def test_finish_does_not_claim_transfer_or_finish_the_other_patient():
    client, ctx = make_client()
    first = ctx.incident
    second = client.post("/api/patients", json={"label": "Patient 2"}, headers=headers(ctx)).json()["incident"]["id"]
    assert client.post("/api/incident", json={}, headers=headers(ctx)).status_code == 409
    done = client.post("/api/encounters/current/finish", headers=headers(ctx)).json()
    assert done["incident"]["id"] == second and done["incident"]["ended_at"]
    assert not done["incident"]["transferred_at"] and first.ended_at is None
    assert client.post(f"/api/patients/{first.id}/activate", headers=headers(ctx)).status_code == 200
    assert ctx.incident is first


def test_stale_patient_requests_cannot_finish_or_switch_the_new_patient():
    client, ctx = make_client()
    old = headers(ctx)
    client.post("/api/incident", json={}, headers=old)
    current = ctx.incident
    for url, body in [("/api/incident", {}), ("/api/incident/end", None),
                      ("/api/encounters/current/finish", None), ("/api/patients", {"label": "Wrong"})]:
        assert client.post(url, json=body, headers=old).status_code == 409
        assert ctx.incident is current and current.ended_at is None
    assert client.post("/api/encounters/current/finish").status_code == 409


def test_next_encounter_keeps_old_outbox_and_restores_it_after_restart(tmp_path):
    options = dict(data_dir=tmp_path / "data", state_key_file=tmp_path / "private" / "key", persistence=True)
    client, ctx = make_client(**options)
    old = ctx.incident
    confirmed(ctx)
    ctx.relay.authorize("First ED")
    ctx.relay.ed_url = "http://127.0.0.1:9999"
    ctx.relay.seq = 19
    ctx.relay.inflight = ctx.relay._build(2000)
    packet = dict(ctx.relay.inflight)
    next_call = client.post("/api/incident", json={"dispatch": "fall"}, headers=headers(ctx)).json()
    assert next_call["incident"]["id"] != old.id
    assert not next_call["facts"] and not next_call["relay"]["authorized"]
    assert next_call["encounter_history"][0]["delivery_pending"]
    saved = ctx.previous_calls[0]
    assert saved.relay.inflight == packet and saved.relay._incidents() == [old]
    restored = build_context(settings_for_test(**options), text_model=FakeModel(name=None), stt=FakeSTT(), vision=FakeVision())
    old_queue = restored.previous_calls[0].relay
    assert old_queue.seq == 20 and old_queue.inflight == packet
    assert old_queue.authorized["destination"] == "First ED"
    assert restored.incident.id == next_call["incident"]["id"] and restored.incident.values() == {}
    sent = []
    async def receive(body):
        wire = json.loads(body)
        sent.append(wire)
        return {"ack": wire["q"]}
    old_queue._transport = receive
    asyncio.run(old_queue.tick(before_send=restored.persist))
    assert sent[0]["i"] == old.id and sent[0]["dest"] == "First ED" and sent[0]["q"] == 20
    report = client.get(f"/api/encounters/{old.id}").json()
    assert "116" in report["handoff"]["text"] and ctx.incident.id == next_call["incident"]["id"]
    assert b"vitals.hr" not in ctx.persistence.path.read_bytes()


def test_finish_survives_restart_and_capture_cannot_reopen_it(tmp_path):
    options = dict(data_dir=tmp_path / "data", state_key_file=tmp_path / "private" / "key", persistence=True)
    client, ctx = make_client(**options)
    patient = ctx.incident.id
    client.post("/api/encounters/current/finish", headers=headers(ctx))
    again, restored = make_client(**options)
    assert restored.incident.id == patient and restored.incident.ended_at is not None
    assert again.post("/api/encounters/resume", headers=headers(restored)).status_code == 409
    assert again.post("/api/capture/auto", json={"on": True, "incident_id": patient}).status_code == 409
    assert not restored.capture_agent.auto


def test_late_verification_does_not_mutate_a_finished_record():
    client, ctx = make_client()
    fact = confirmed(ctx)
    client.post("/api/encounters/current/finish", headers=headers(ctx))
    with pytest.raises(IncidentEnded):
        ctx.incident.hold_verification(fact.id, "late result")
    assert fact.status == Status.confirmed


def test_recovered_patient_requires_explicit_resume_before_capture(tmp_path):
    options = dict(data_dir=tmp_path / "data", state_key_file=tmp_path / "private" / "key", persistence=True)
    _, ctx = make_client(**options)
    ctx.persist()
    client, restored = make_client(**options)
    assert restored.restored
    assert client.post("/api/capture/auto", json={"on": True}).status_code == 409
    assert client.post("/api/encounters/resume", headers=headers(restored)).status_code == 200
    assert not restored.restored
    assert client.post("/api/capture/auto", json={"on": True}).status_code == 200


def test_standalone_protocol_request_does_not_extract_patient_facts():
    from herald.knowledge.cues import ProtocolCues
    model = FakeModel(rows=[{"k": "meds.anticoagulant", "v": "warfarin", "r": "medic", "c": 0.99}])
    client, ctx = make_client(model=model)
    ctx.cues = ProtocolCues(lambda: None, lambda: "santa_clara")
    response = client.post("/api/transcript", json={"text": "Show me the protocol for anticoagulants", "captured_by": "medic"})
    assert response.status_code == 200
    assert model.calls == 0 and not ctx.incident.facts
    assert ctx.incident.transcripts[-1]["asked"] is True


def test_restored_same_scene_new_patient_keeps_the_original_dispatch(tmp_path):
    options = dict(data_dir=tmp_path / "data", state_key_file=tmp_path / "private" / "key", persistence=True)
    client, ctx = make_client(**options)
    client.post("/api/incident", json={"dispatch": "fall"}, headers=headers(ctx))
    again, restored = make_client(**options)
    again.post("/api/patients", json={"label": "Patient 2"}, headers=headers(restored))
    assert restored.incident.dispatch == "fall"
