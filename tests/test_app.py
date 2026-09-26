"""HTTP/WebSocket behaviour the screens rely on: heartbeat, monitor-panel and failed-photo trace
entries, all-or-nothing structured facts, and the /classic/ safety-net page."""
import io
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
import pytest

from ed_receiver import app as ed_mod
from fakes import FakeModel, FakeSTT, FakeVision, make_client, test_settings as fake_settings
from herald.api import build_context, create_app
from herald.api.persistence import IncidentStore, PersistenceError
from herald.core.schema import CapturedBy, FactIn, Role

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
    assert all(f["status"] == "unconfirmed" for f in r.json())


def test_structured_endpoint_cannot_forge_a_confirmed_medic_fact():
    c, _ = make_client()
    r = c.post("/api/facts", json=[{"key": "allergies", "value": ["penicillin"],
                                     "captured_by": "medic", "role": "medic", "speaker": "medic",
                                     "confidence": 1.0}])
    assert r.status_code == 200
    fact = r.json()[0]
    assert (fact["captured_by"], fact["role"], fact["speaker"], fact["confidence"], fact["status"]) == \
        ("device", "device", "monitor", 0.0, "unconfirmed")
    assert "confirm before relay" in fact["provenance"]["hold_reason"]


def test_bulk_confirm_skips_held_facts_and_reports_missing_ids():
    c, _ = make_client()
    first = c.post("/api/facts", json=[{"key": "vitals.hr", "value": 80, **MONITOR}]).json()[0]
    second = c.post("/api/facts", json=[{"key": "vitals.hr", "value": 120, **MONITOR}]).json()[0]
    r = c.post("/api/facts/confirm", json={"ids": [first["id"], second["id"], "missing"]})
    assert r.status_code == 200 and r.json()["confirmed"] == []
    assert {row["reason"] for row in r.json()["skipped"]} == {"held fact requires individual review", "not found"}


def test_structured_facts_are_all_or_nothing():
    c, _ = make_client()
    r = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR},
                                   {"key": "vitals.nope", "value": 1, **MONITOR}])
    assert r.status_code == 400
    s = c.get("/api/state").json()
    assert not s["facts"] and s["transcripts"] == []


def test_medic_can_correct_a_fact_without_rewriting_history():
    c, _ = make_client()
    original = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR}]).json()[0]
    r = c.post(f"/api/facts/{original['id']}/correct", json={"value": 138})
    assert r.status_code == 200
    state = c.get("/api/state").json()
    assert state["facts"]["vitals.sbp"]["value"] == 138
    old = next(f for f in state["timeline"] if f["id"] == original["id"])
    assert old["status"] == "rejected"
    corrected = state["facts"]["vitals.sbp"]
    assert corrected["status"] == "confirmed"
    assert corrected["provenance"]["extractor"] == "manual-correction"
    assert "Corrected Systolic BP" in state["transcripts"][-1]["text"]
    assert corrected["previous_value"] == 150


@pytest.mark.parametrize("value", [None, "", "150", True, -1, 400, 120.5])
def test_invalid_correction_does_not_change_original(value):
    c, _ = make_client()
    original = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR}]).json()[0]
    assert c.post(f"/api/facts/{original['id']}/correct", json={"value": value}).status_code == 400
    state = c.get("/api/state").json()
    assert state["facts"]["vitals.sbp"]["id"] == original["id"]
    assert len(state["timeline"]) == 1


def test_stale_or_repeated_correction_is_not_applied_twice():
    c, _ = make_client()
    original = c.post("/api/facts", json=[{"key": "allergies", "value": ["aspirin"], **MONITOR}]).json()[0]
    url = f"/api/facts/{original['id']}/correct"
    assert c.post(url, json={"value": []}).status_code == 200
    assert c.post(url, json={"value": ["penicillin"]}).status_code == 409
    state = c.get("/api/state").json()
    assert state["facts"]["allergies"]["value"] == []
    assert len(state["timeline"]) == 2


def test_correction_cannot_cross_incidents():
    c, _ = make_client()
    original = c.post("/api/facts", json=[{"key": "vitals.sbp", "value": 150, **MONITOR}]).json()[0]
    c.post("/api/incident", json={"dispatch": "next patient", "disposition": "transported"})
    assert c.post(f"/api/facts/{original['id']}/correct", json={"value": 138}).status_code == 404
    assert not c.get("/api/state").json()["facts"]


def test_patient_identifiers_always_require_verification():
    c, _ = make_client()
    facts = c.post("/api/facts", json=[
        {"key": "patient.name", "value": "Test Patient", **MONITOR},
        {"key": "patient.identifier", "value": "DEMO-123", **MONITOR},
    ]).json()
    assert all(f["status"] == "unconfirmed" for f in facts)


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


def test_ed_receiver_removes_withdrawn_facts_once_and_keeps_an_audit_event():
    c = TestClient(ed_mod.app)
    c.post("/reset")
    c.post("/ingest", json={"i": "inc-1", "q": 1, "tier": "critical", "f": {"meds.anticoagulant": True}, "x": 0})
    assert c.post("/ingest", json={"i": "inc-1", "q": 2, "tier": "critical", "f": {},
                                    "rm": ["meds.anticoagulant"], "x": 0}).json() == {"ack": 2}
    state = c.get("/state").json()["incidents"]["inc-1"]
    assert "meds.anticoagulant" not in state["fields"]
    assert state["audit"][-1]["action"] == "withdrawn"
    c.post("/ingest", json={"i": "inc-1", "q": 2, "tier": "critical", "f": {},
                              "rm": ["meds.anticoagulant"], "x": 0})
    assert len(c.get("/state").json()["incidents"]["inc-1"]["audit"]) == 1


def test_ed_receiver_records_human_acknowledgement():
    c = TestClient(ed_mod.app)
    c.post("/reset")
    c.post("/ingest", json={"i": "inc-1", "q": 1, "tier": "critical", "f": {}, "x": 0})
    response = c.post("/incidents/inc-1/acknowledgements", json={"status": "received", "note": "triage notified"})
    assert response.status_code == 200 and response.json()["status"] == "received"
    assert c.get("/state").json()["incidents"]["inc-1"]["acknowledgements"][0]["note"] == "triage notified"


def test_unfinished_call_is_restored_from_an_encrypted_local_file(tmp_path):
    key_path = tmp_path / "private" / "state.key"
    settings = fake_settings(data_dir=tmp_path / "data", persistence=True, state_key_file=key_path)
    first = build_context(settings, text_model=FakeModel(name=None), stt=FakeSTT(), vision=FakeVision())
    first.incident.ingest(FactIn(key="vitals.hr", value=116, captured_by=CapturedBy.medic, role=Role.medic,
                                 confidence=0.99))
    first.persist()
    stored = settings.state_dir / "active-call.fernet"
    assert stored.exists() and b"vitals.hr" not in stored.read_bytes()
    assert key_path.parent != settings.state_dir
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    restored = build_context(settings, text_model=FakeModel(name=None), stt=FakeSTT(), vision=FakeVision())
    assert restored.restored is True and restored.incident.values()["vitals.hr"] == 116
    restored.end_incident()
    assert stored.exists()
    closed = build_context(settings, text_model=FakeModel(name=None), stt=FakeSTT(), vision=FakeVision())
    assert closed.incident.ended_at and closed.incident.values()["vitals.hr"] == 116
    assert key_path.exists()                         # retained separately for the next unfinished call


def test_relay_authorization_is_saved_with_an_unfinished_call(tmp_path):
    key_path = tmp_path / "private" / "state.key"
    settings = fake_settings(data_dir=tmp_path / "data", persistence=True, state_key_file=key_path)
    client, _ = make_client(data_dir=tmp_path / "data", persistence=True, state_key_file=key_path)
    client.post("/api/relay/authorize", json={"destination": "Valley ED"})
    restored = build_context(settings, text_model=FakeModel(name=None), stt=FakeSTT(), vision=FakeVision())
    assert restored.relay.authorized["destination"] == "Valley ED"


def test_recovery_refuses_tampering_missing_keys_and_weak_key_permissions(tmp_path):
    state_dir, key_path = tmp_path / "data" / "state", tmp_path / "private" / "state.key"
    store = IncidentStore(state_dir, key_path)
    store.save({"v": 1, "patients": [{"id": "inc-1"}]})
    token = bytearray(store.path.read_bytes())
    token[-1] ^= 1
    store.path.write_bytes(token)
    with pytest.raises(PersistenceError, match="failed authentication"):
        store.load()

    store.save({"v": 1})
    key_path.unlink()
    with pytest.raises(PersistenceError, match="key is missing"):
        store.load()

    store.path.unlink()
    store.save({"v": 1})
    os.chmod(key_path, 0o644)
    with pytest.raises(PersistenceError, match="permissions must be 0600"):
        store.load()


def test_recovery_key_must_be_outside_patient_data_directory(tmp_path):
    with pytest.raises(ValueError, match="outside HERALD_DATA_DIR"):
        IncidentStore(tmp_path / "data" / "state", tmp_path / "data" / "keys" / "state.key")


def test_concurrent_recovery_saves_leave_one_authenticated_snapshot(tmp_path):
    store = IncidentStore(tmp_path / "data" / "state", tmp_path / "private" / "state.key")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: store.save({"v": 1, "revision": n}), range(40)))
    assert store.load()["revision"] in range(40)


def test_relay_scope_is_derived_from_the_active_checklist_not_the_client_label():
    c, _ = make_client(dispatch="fall")
    response = c.post("/api/relay/authorize", json={"destination": "Valley Medical", "scope": "stroke pre-alert set"})
    assert response.status_code == 200
    assert response.json()["authorized"]["scope"] == "Trauma Alert pre-alert set"

    c.post("/api/incident", json={"dispatch": "unknown", "disposition": "transported"})
    response = c.post("/api/relay/authorize", json={"destination": "Valley Medical"})
    assert response.json()["authorized"]["scope"] == "patient update set"


def test_changing_ed_url_clears_the_previous_receivers_acknowledgements():
    c, context = make_client()
    context.egress.allow_hosts |= {"ed-a", "ed-b"}   # B7: /api/relay/config only accepts an allow-listed ED host
    c.post("/api/facts", json=[{"key": "vitals.hr", "value": 90, **MONITOR}])
    fact_id = c.get("/api/state").json()["facts"]["vitals.hr"]["id"]
    c.post(f"/api/facts/{fact_id}/confirm")
    context.relay.acked[context.incident.id] = {"vitals.hr": 90}
    c.post("/api/relay/authorize", json={"destination": "ED A"})
    c.post("/api/relay/config", json={"ed_url": "http://ed-a"})
    assert context.relay.acked == {}
    context.relay.acked[context.incident.id] = {"vitals.hr": 90}
    context.relay.clinician_acknowledgements[context.incident.id] = [{"status": "received"}]
    c.post("/api/relay/config", json={"ed_url": "http://ed-b"})
    assert context.relay.acked == {}
    assert context.relay.clinician_acknowledgements == {}


def wav_bytes():
    buf = io.BytesIO()
    sf.write(buf, np.zeros(800, dtype=np.float32), 16000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_stt_failure_keeps_audio_and_an_explicit_trace_entry(tmp_path):
    class BrokenSTT:
        model = "broken-stt"

        def ready(self):
            return False

        def transcribe(self, *_args):
            raise RuntimeError("microphone backend unavailable")

    context = build_context(fake_settings(data_dir=tmp_path), text_model=FakeModel(name=None), stt=BrokenSTT(),
                            vision=FakeVision())
    client = TestClient(create_app(context))
    response = client.post("/api/audio", files={"file": ("clip.wav", wav_bytes(), "audio/wav")})
    assert response.status_code == 503 and "recording kept" in response.json()["detail"]
    entry = client.get("/api/state").json()["transcripts"][-1]
    assert entry["stt"]["error"] == "microphone backend unavailable"
    assert entry["trace"]["model"]["status"] == "error"
    assert client.get(f"/api/audio/{entry['audio_id']}").status_code == 200


def test_words_kept_while_the_model_is_down_can_be_retried_without_a_new_transcript():
    model = FakeModel(name=None)
    client, _ = make_client(model)
    assert client.post("/api/transcript", json={"text": "pulse 88"}).status_code == 503
    entry_id = client.get("/api/state").json()["transcripts"][-1]["id"]

    assert client.post(f"/api/transcripts/{entry_id}/retry").status_code == 503
    model.name = "recovered-model"
    response = client.post(f"/api/transcripts/{entry_id}/retry")
    assert response.status_code == 200 and response.json()["transcript"]["id"] == entry_id
    assert len(client.get("/api/state").json()["transcripts"]) == 1


def test_end_incident_deletes_only_that_calls_audio_and_photos_and_is_idempotent(tmp_path):
    client, context = make_client(data_dir=tmp_path)
    assert client.post("/api/audio", files={"file": ("clip.wav", wav_bytes(), "audio/wav")}).status_code == 200
    photo = client.post("/api/photo", files={"file": ("x.jpg", b"\xff\xd8fake", "image/jpeg")},
                        data={"mode": "monitor"}).json()["photo_id"]
    audio = next(iter(context.incident.media_ids["audio"]))
    unrelated = context.settings.audio_dir / "a_0123456789.wav"
    unrelated.write_bytes(b"another call")

    response = client.post("/api/incident/end")
    assert response.status_code == 200
    cleanup = response.json()
    assert cleanup["deleted"] == {"audio": [audio], "photo": [photo]}
    assert not cleanup["missing"]["audio"] and not cleanup["invalid"]["photo"]
    assert client.get(f"/api/audio/{audio}").status_code == 404
    assert client.get(f"/api/photo/{photo}").status_code == 404
    assert unrelated.read_bytes() == b"another call"
    assert client.get("/api/state").json()["incident"]["ended_at"] == cleanup["at"]
    assert client.post("/api/facts", json=[{"key": "vitals.hr", "value": 80, **MONITOR}]).status_code == 409
    assert client.post("/api/incident/end").json() == cleanup


def test_starting_a_new_incident_disposes_the_previous_calls_media(tmp_path):
    client, context = make_client(data_dir=tmp_path)
    client.post("/api/audio", files={"file": ("clip.wav", wav_bytes(), "audio/wav")})
    old_id = context.incident.id
    audio = next(iter(context.incident.media_ids["audio"]))

    response = client.post("/api/incident", json={"dispatch": "fall", "disposition": "transported"})
    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["id"] != old_id and body["incident"]["ended_at"] is None
    assert body["previous_call_cleanup"]["deleted"]["audio"] == [audio]
    assert client.get(f"/api/audio/{audio}").status_code == 404


def test_ending_a_multi_patient_call_disposes_every_patients_media(tmp_path):
    client, context = make_client(data_dir=tmp_path)
    client.post("/api/audio", files={"file": ("driver.wav", wav_bytes(), "audio/wav")})
    driver_audio = next(iter(context.incident.media_ids["audio"]))
    client.post("/api/patients", json={"label": "Passenger"})
    client.post("/api/audio", files={"file": ("passenger.wav", wav_bytes(), "audio/wav")})
    passenger_audio = next(iter(context.incident.media_ids["audio"]))

    cleanup = client.post("/api/incident/end").json()

    assert cleanup["deleted"]["audio"] == sorted([driver_audio, passenger_audio])
    assert set(cleanup["patients"]) == {inc.id for inc in context.roster.incidents()}
    assert all(inc.ended_at is not None for inc in context.roster.incidents())
    assert client.post("/api/patients", json={"label": "Late patient"}).status_code == 200
    assert context.incident.ended_at is None


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
