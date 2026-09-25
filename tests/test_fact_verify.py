"""The check step on overheard speech (herald/extraction/verify.py): the extraction model proposes, a second model read
keeps only what the words say about the patient, and overheard words with nothing clinical leave the record."""
import io
import time

import numpy as np
import soundfile as sf

from fakes import FakeModel, make_client
from herald.core.schema import FactIn
from herald.extraction.verify import FactVerifier


class _Judge:
    """A model that answers the verifier's question from a script: {fact number: keep}."""

    def __init__(self, keep: dict[int, bool], fail: bool = False):
        self.keep, self.fail, self.seen = keep, fail, []

    def chat_json(self, system, user, *, schema=None, max_tokens=256, **_):
        self.seen.append((system, user))
        if self.fail:
            raise RuntimeError("model down")
        return {"facts": [{"n": n, "keep": k, "why": "scripted"} for n, k in self.keep.items()]}


def test_the_verifier_discards_what_it_rejects_and_keeps_the_rest():
    judge = _Judge({1: False, 2: True})
    kept, gone = FactVerifier(judge).check("So, khatam toho, model calls me ja. Pulse ninety five.",
                                           [FactIn(key="stroke.deficits", value=["model calls me ja"]),
                                            FactIn(key="vitals.hr", value=95)], "possible stroke")
    assert [f.key for f in kept] == ["vitals.hr"]
    assert gone == [{"key": "stroke.deficits", "value": ["model calls me ja"], "why": "scripted"}]
    system, user = judge.seen[0]
    assert "overheard" in system.lower() and "model calls me ja" in user and "[2] vitals.hr = 95" in user


def test_a_fact_the_model_did_not_answer_for_is_kept_for_a_tap():
    kept, gone = FactVerifier(_Judge({1: False})).check("x", [FactIn(key="vitals.hr", value=95),
                                                              FactIn(key="vitals.spo2", value=93)])
    assert [f.key for f in kept] == ["vitals.spo2"] and len(gone) == 1


def _recording():
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(16000), 16000, format="WAV", subtype="PCM_16")
    return {"file": ("clip.wav", buffer.getvalue(), "audio/wav")}


class _SaidSTT:
    model = "scripted"

    def __init__(self, text):
        self.text = text

    def ready(self):
        return True

    def transcribe(self, audio, sr, language=None):
        return {"text": self.text, "chunks": [], "seconds": 1.0, "language": "en"}


def _overhear(tmp_path, words, rows, judge):
    client, ctx = make_client(model=FakeModel(rows=rows), audio_dir=tmp_path)
    ctx.stt, ctx.fact_verifier = _SaidSTT(words), FactVerifier(judge)
    with client:
        assert client.post("/api/audio", files=_recording(),
                           data={"incident_id": ctx.incident.id, "ambient": "true"}).status_code == 200
        deadline = time.monotonic() + 2
        while ctx.speech_in_flight and time.monotonic() < deadline:
            time.sleep(.01)
    return ctx


def test_overheard_words_whose_only_fact_is_rejected_leave_the_record_and_their_audio_is_deleted(tmp_path):
    ctx = _overhear(tmp_path, "My back is killing me from that carry.", [["complaint.chief", "back pain", "u"]],
                    _Judge({1: False}))
    assert not ctx.incident.facts
    assert ctx.incident.transcripts == []                     # nothing clinical: not part of the call's record
    assert not ctx.incident.media_ids["audio"] and not list(tmp_path.glob("*.wav"))
    assert ctx.telemetry.snapshot()["stt_dropped"].get("nothing clinical") == 1


def test_overheard_words_with_a_kept_fact_stay_with_the_rejected_one_in_the_trace(tmp_path):
    ctx = _overhear(tmp_path, "Pulse ninety five, model calls me ja.",
                    [["vitals.hr", 95, "u"], ["stroke.deficits", ["model calls me ja"], "u"]], _Judge({1: True, 2: False}))
    assert [f.key for f in ctx.incident.facts] == ["vitals.hr"]
    entry = ctx.incident.transcripts[-1]
    assert [d["key"] for d in entry["trace"]["model"]["discarded"]] == ["stroke.deficits"]


def test_when_the_check_cannot_run_every_proposal_stays_unconfirmed(tmp_path):
    ctx = _overhear(tmp_path, "Pulse ninety five.", [["vitals.hr", 95, "u"]], _Judge({}, fail=True))
    assert [f.key for f in ctx.incident.facts] == ["vitals.hr"]
    assert ctx.incident.facts[0].status.value == "unconfirmed"
    assert "not checked" in ctx.incident.transcripts[-1]["trace"]["model"]["discarded"][0]["error"]


def test_the_medics_own_words_are_never_second_guessed_or_forgotten(tmp_path):
    client, ctx = make_client(model=FakeModel(rows=[]))
    judge = _Judge({1: False})
    ctx.fact_verifier = FactVerifier(judge)
    with client:
        client.post("/api/transcript", json={"text": "Let me check the other arm.", "captured_by": "medic"})
        deadline = time.monotonic() + 2
        while ctx.speech_in_flight and time.monotonic() < deadline:
            time.sleep(.01)
    assert len(ctx.incident.transcripts) == 1 and not judge.seen
