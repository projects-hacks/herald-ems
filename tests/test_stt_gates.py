"""The speech gates (herald/models/stt_gates.py, config/stt.yaml): a clip Whisper itself says holds no speech, a
language Herald does not read, or a decode that looped never reaches the record. Live on 2026-09-25 a silent
ambient clip came back as an echo of the priming prompt's values and a blood pressure nobody said was extracted."""
import io
import re
import time

import numpy as np
import soundfile as sf

from fakes import FakeModel, make_client
from herald.api.capture import AMBIENT_SPEAKER
from herald.config import load_text, load_yaml
from herald.models.stt import WhisperSTT
from herald.models.stt_gates import ClipSignals, SpeechGates, compression_ratio
from herald.telemetry import Telemetry

SPEECH = ClipSignals(no_speech_prob=0.02, language="en", language_prob=0.98, read_prob=0.99)
SILENCE = ClipSignals(no_speech_prob=0.97, language="en", language_prob=0.40, read_prob=0.45)
RUSSIAN = ClipSignals(no_speech_prob=0.10, language="ru", language_prob=0.90, read_prob=0.05)
NOISE = ClipSignals(no_speech_prob=0.0, language="en", language_prob=0.50, read_prob=0.62)   # turbo on cabin noise
LOOP = "BP 182, RACE, " + "NEWS3, " * 100
CLIP = np.zeros(16000 * 8, np.float32)


# ---------- the gates themselves ----------
def test_thresholds_and_languages_are_content_with_whispers_defaults():
    cfg = load_yaml("stt.yaml")["gates"]
    g = SpeechGates.from_config()
    assert (g.no_speech_threshold, g.compression_ratio_threshold) == (0.6, 2.4)     # openai-whisper transcribe()
    assert (g.no_speech_threshold, g.compression_ratio_threshold) == \
        (cfg["no_speech_threshold"], cfg["compression_ratio_threshold"])
    assert g.languages == frozenset(cfg["languages"]) == {"en", "es"}               # English and Mexican Spanish
    assert g.min_read_language_prob == cfg["min_read_language_prob"] == 0.85         # measured, MODEL_PLAN §0k


def test_no_speech_above_the_threshold_is_dropped_before_any_text_is_decoded():
    g = SpeechGates(0.6, 2.4, ["en", "es"])
    assert g.before_decoding(SILENCE) == "no speech"
    assert g.before_decoding(ClipSignals(0.6, "en", 0.9)) is None       # the threshold itself passes, as in Whisper


def test_a_language_herald_does_not_read_is_dropped():
    g = SpeechGates(0.6, 2.4, ["en", "es"])
    assert g.before_decoding(RUSSIAN) == "language"
    assert g.before_decoding(ClipSignals(0.1, "es", 0.9)) is None


def test_a_clip_whisper_cannot_place_in_a_read_language_is_dropped_but_code_switching_is_not():
    g = SpeechGates(0.6, 2.4, ["en", "es"], min_read_language_prob=0.85)
    assert g.before_decoding(NOISE) == "language"                       # "some language, unsure which": not speech
    assert g.before_decoding(ClipSignals(0.0, "en", 0.55, read_prob=0.98)) is None   # English and Spanish mixed
    assert SpeechGates(0.6, 2.4, ["en", "es"]).before_decoding(NOISE) is None        # off when unset (0.0)
    assert SpeechGates.from_config().before_decoding(NOISE) == "language"


def test_a_repetition_loop_is_dropped_after_decoding_and_speech_is_not():
    g = SpeechGates(0.6, 2.4, ["en", "es"])
    assert compression_ratio(LOOP) > 2.4 and g.after_decoding(compression_ratio(LOOP)) == "repetition loop"
    said = "72 year old on apixaban, pulse 92, BP 182 over 104, last known well 1:40, left facial droop"
    assert compression_ratio(said) < 2.4 and g.after_decoding(compression_ratio(said)) is None
    assert compression_ratio("") == 0.0


def test_normal_speech_passes_both_gates():
    g = SpeechGates.from_config()
    assert g.before_decoding(SPEECH) is None
    assert g.after_decoding(compression_ratio("heart rate 95, sat 97 on room air")) is None


# ---------- WhisperSTT over a fake pipeline: what it decodes, what it reports ----------
class _Pipe:
    """Stands in for the transformers pipeline; records every decode it was asked for."""

    def __init__(self, text: str):
        self.text, self.calls, self.tokenizer = text, [], None

    def __call__(self, x, generate_kwargs, return_timestamps, batch_size=None):
        self.calls.append(generate_kwargs)
        if isinstance(x, list):
            return [{"text": f" {self.text}", "chunks": []} for _ in x]
        return {"text": f" {self.text}", "chunks": [{"text": self.text, "timestamp": (0.0, 1.0)}]}


def _stt(signals, text):
    stt = WhisperSTT("unused", usage=Telemetry())
    stt._pipe = _Pipe(text)
    stt._signals = lambda clips: [signals for _ in clips]
    return stt


def test_a_silent_clip_is_dropped_without_decoding_and_the_reason_is_counted():
    stt = _stt(SILENCE, "Thank you.")
    out = stt.transcribe(CLIP, 16000)
    assert out["text"] == "" and out["chunks"] == [] and out["dropped"] == "no speech"
    assert out["language"] == "en" and out["signals"]["no_speech_prob"] == 0.97 and out["seconds"] == 8.0
    assert out["signals"]["read_language_prob"] == 0.45
    assert stt._pipe.calls == []                                   # the decoder never ran
    assert stt.usage.stt_dropped == {"no speech": 1} and stt.usage.stt_calls == 1


def test_a_clip_in_another_language_is_dropped_and_names_the_language():
    stt = _stt(RUSSIAN, "Редактор субтитров А.Семкин")
    out = stt.transcribe(CLIP, 16000)
    assert out["text"] == "" and out["dropped"] == "language" and out["language"] == "ru"
    assert stt._pipe.calls == [] and stt.usage.stt_dropped == {"language": 1}


def test_a_looping_decode_is_discarded():
    stt = _stt(SPEECH, LOOP)
    out = stt.transcribe(CLIP, 16000)
    assert out["text"] == "" and out["chunks"] == [] and out["dropped"] == "repetition loop"
    assert out["signals"]["compression_ratio"] > 2.4
    assert len(stt._pipe.calls) == 1 and stt.usage.stt_dropped == {"repetition loop": 1}


def test_speech_passes_and_the_language_heard_goes_with_the_decode():
    stt = _stt(ClipSignals(0.01, "es", 0.99, 0.99), "presión ciento ochenta sobre cien")
    out = stt.transcribe(CLIP, 16000)
    assert out["text"] == "presión ciento ochenta sobre cien" and "dropped" not in out
    assert out["language"] == "es" and out["chunks"][0]["t"] == [0.0, 1.0]
    assert stt._pipe.calls[0]["language"] == "es"                  # not detected a second time by generation
    assert stt.transcribe(CLIP, 16000, language="en")["text"] and stt._pipe.calls[1]["language"] == "en"
    assert stt.usage.stt_dropped == {} and stt.usage.stt_calls == 2


def test_transcribe_many_applies_the_same_gates_keeps_order_and_can_measure_ungated():
    stt = _stt(SPEECH, "pulse 92")
    per_clip = iter([SPEECH, SILENCE, RUSSIAN])
    stt._signals = lambda clips: [next(per_clip) for _ in clips]
    out = stt.transcribe_many([CLIP, CLIP, CLIP], 16000, batch_size=8)
    assert [o["text"] for o in out] == ["pulse 92", "", ""]
    assert [o.get("dropped") for o in out] == [None, "no speech", "language"]
    assert [o["language"] for o in out] == ["en", "en", "ru"]
    assert len(stt._pipe.calls) == 1 and "language" not in stt._pipe.calls[0]     # one batch of the kept clip
    assert stt.usage.stt_dropped == {"no speech": 1, "language": 1}

    loops = _stt(SPEECH, LOOP)
    ungated = loops.transcribe_many([CLIP, CLIP], 16000, gate=False)
    assert [o["text"] for o in ungated] == [LOOP.strip(), LOOP.strip()] and not any("dropped" in o for o in ungated)
    assert [o["language"] for o in ungated] == [None, None]


def test_warm_runs_the_decoder_although_silence_would_be_gated():
    stt = _stt(SILENCE, "")
    stt.warm()
    assert len(stt._pipe.calls) == 1 and stt.usage.stt_calls == 0


def test_the_priming_prompt_is_vocabulary_only_and_its_echo_is_still_stripped():
    prompt = load_text("prompts/stt_prompt.txt")
    assert not re.search(r"\b\d", prompt), "no values in the prompt: an echo must not read as a vital sign"
    stt = _stt(SPEECH, f"{prompt} pulse 92")
    assert stt.transcribe(CLIP, 16000)["text"] == "pulse 92"


# ---------- the capture path: a dropped clip is nothing heard ----------
def _recording():
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(16000), 16000, format="WAV", subtype="PCM_16")
    return {"file": ("clip.wav", buffer.getvalue(), "audio/wav")}


class _ScriptedSTT:
    model = "scripted"

    def __init__(self, result):
        self.result = result

    def ready(self):
        return True

    def transcribe(self, audio, sr, language=None):
        return dict(self.result)


def test_a_dropped_clip_makes_no_transcript_no_facts_and_no_extraction_call(tmp_path):
    model = FakeModel(rows=[["vitals.sbp", 182, "m"]])
    client, ctx = make_client(model=model, audio_dir=tmp_path)
    ctx.stt = _ScriptedSTT({"text": "", "chunks": [], "seconds": 8.0, "language": "ru", "dropped": "language",
                            "signals": {"no_speech_prob": 0.1, "language_prob": 0.9, "compression_ratio": 0.0}})
    with client:
        r = client.post("/api/audio", files=_recording(), data={"incident_id": ctx.incident.id, "ambient": "true"})
        assert r.status_code == 200
        body = r.json()
        assert body["transcript"] is None and body["facts"] == [] and body["stt"]["dropped"] == "language"
        state = client.get("/api/state").json()
    assert state["transcripts"] == [] and not ctx.incident.transcripts and not ctx.incident.facts
    assert model.calls == 0


def test_a_kept_ambient_clip_is_heard_from_an_unidentified_speaker_in_its_language(tmp_path):
    model = FakeModel(rows=[["vitals.hr", 95, "m"]])
    client, ctx = make_client(model=model, audio_dir=tmp_path)
    ctx.stt = _ScriptedSTT({"text": "heart rate 95", "chunks": [], "seconds": 8.0, "language": "en",
                            "signals": {"no_speech_prob": 0.01, "language_prob": 0.99, "compression_ratio": 1.1}})
    with client:
        r = client.post("/api/audio", files=_recording(), data={"incident_id": ctx.incident.id, "ambient": "true"})
        assert r.status_code == 200
        deadline = time.monotonic() + 2
        while not ctx.incident.facts and time.monotonic() < deadline:
            time.sleep(.01)
    entry = ctx.incident.transcripts[-1]
    assert entry["speaker"] == AMBIENT_SPEAKER == "Speaker not identified"
    assert entry["stt"]["language"] == "en" and entry["trace"]["heard"]["stt"]["language"] == "en"
    assert "signals" not in entry["stt"] and "dropped" not in entry["stt"]      # no model internals on the screen
    assert ctx.incident.facts and ctx.incident.facts[0].speaker == AMBIENT_SPEAKER


def test_telemetry_counts_dropped_clips_by_reason():
    t = Telemetry()
    t.record_stt(8.0)
    t.record_stt_dropped("no speech")
    t.record_stt_dropped("no speech")
    t.record_stt_dropped("repetition loop")
    s = t.snapshot(model=None)
    assert s["stt_dropped"] == {"no speech": 2, "repetition loop": 1}
    assert s["calls"]["stt"] == 1 and s["stt_audio_min"] == round(8.0 / 60, 2)      # the audio still counts
    client, ctx = make_client()
    ctx.telemetry.record_stt_dropped("language")
    assert client.get("/api/telemetry").json()["stt_dropped"] == {"language": 1}
