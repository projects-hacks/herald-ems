"""Capture queues must not leak facts across patients or infer ambient speaker identity."""
import asyncio
import io

import numpy as np
import soundfile as sf

from fakes import make_client
from herald.api.capture import CaptureService
from herald.core.schema import CapturedBy, FactIn, Role


def recording():
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(1600), 16000, format="WAV", subtype="PCM_16")
    return {"file": ("clip.wav", buffer.getvalue(), "audio/wav")}


def test_stale_audio_rejected_before_transcription(tmp_path):
    client, ctx = make_client(audio_dir=tmp_path)
    result = client.post("/api/audio", files=recording(), data={"incident_id": "previous-patient"})
    assert result.status_code == 409
    assert not list(tmp_path.iterdir())
    assert not ctx.incident.facts


def test_stale_photo_rejected_before_vision(tmp_path):
    client, ctx = make_client(photo_dir=tmp_path)
    result = client.post("/api/photo", files={"file": ("photo.jpg", b"image", "image/jpeg")},
                         data={"incident_id": "previous-patient"})
    assert result.status_code == 409
    assert not ctx.incident.facts
    assert not list(tmp_path.iterdir())


def test_patient_switch_during_stt_does_not_add_transcript(tmp_path):
    client, ctx = make_client(audio_dir=tmp_path)

    class SwitchingSTT:
        def transcribe(self, audio, sr, language):
            ctx.new_incident("new patient")
            return {"text": "heart rate 95", "seconds": 0.1, "chunks": []}

    ctx.stt = SwitchingSTT()
    result = client.post("/api/audio", files=recording(), data={"incident_id": ctx.incident.id})
    assert result.status_code == 409
    assert not ctx.incident.transcripts
    assert not ctx.incident.facts


def test_ambient_audio_cannot_claim_medic_identity(tmp_path):
    client, ctx = make_client(audio_dir=tmp_path)

    class Speech:
        def transcribe(self, audio, sr, language):
            return {"text": "heart rate 95", "seconds": 0.1, "chunks": []}

    ctx.stt = Speech()
    result = client.post("/api/audio", files=recording(), data={
        "incident_id": ctx.incident.id, "ambient": "true", "captured_by": "medic", "use_llm": "false"})
    assert result.status_code == 200
    facts = result.json()["facts"]
    assert facts
    for fact in facts:
        assert fact["captured_by"] == "other"
        assert fact["role"] == "unknown"
        assert fact["status"] == "unconfirmed"
        assert "Ambient speech" in fact["provenance"]["hold_reason"]


def test_request_scoped_capture_retains_original_incident():
    _, ctx = make_client()

    async def broadcast():
        pass

    scoped = CaptureService(ctx, broadcast).for_incident()
    previous = ctx.incident
    ctx.new_incident("next patient")
    scoped.ambient = True
    facts = scoped.ingest_batch([FactIn(key="vitals.hr", value=95, confidence=1,
                                       captured_by=CapturedBy.medic, role=Role.medic)])
    assert scoped.inc is previous
    assert facts[0].status.value == "unconfirmed"
    assert not ctx.incident.facts


def test_patient_switch_during_photo_does_not_pollute_new_incident(tmp_path):
    client, ctx = make_client(photo_dir=tmp_path)
    previous = ctx.incident

    class SwitchingVision:
        def read(self, raw, mode, photo_id):
            ctx.new_incident("next patient")
            return [FactIn(key="vitals.hr", value=95, captured_by=CapturedBy.camera, role=Role.photo)]

    ctx.vision = SwitchingVision()
    result = client.post("/api/photo", files={"file": ("photo.jpg", b"image", "image/jpeg")},
                         data={"incident_id": previous.id})
    assert result.status_code == 200
    assert previous.transcripts
    assert not ctx.incident.transcripts
    assert not ctx.incident.facts


def test_model_refinement_retains_original_incident():
    _, ctx = make_client()
    previous = ctx.incident

    async def broadcast():
        pass

    class SwitchingExtractor:
        last_usage = {}

        def extract(self, *args):
            ctx.new_incident("next patient")
            return [FactIn(key="vitals.hr", value=95, captured_by=CapturedBy.medic, role=Role.medic)]

    ctx.model_extractor = SwitchingExtractor()
    scoped = CaptureService(ctx, broadcast).for_incident()
    scoped.ambient = True
    entry = {"fact_ids": [], "extract": {}, "trace": {"effects": {}}}
    asyncio.run(scoped._refine(entry, "heart rate 95", CapturedBy.other, Role.unknown, None, None, []))
    assert entry["trace"]["model"]["status"] == "done"
    assert entry["trace"]["model"]["facts"][0]["role"] == "unknown"
    assert scoped.inc is previous
    assert not ctx.incident.facts
