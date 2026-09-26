"""Measured ASR layer (scripts/asr_layer.py, scripts/cabin_noise.py, WhisperSTT.transcribe_many; MODEL_PLAN §0k
"Measured ASR noise"): which transcripts may teach the extractor, the noise mix, and the batched speech path."""
import json

import numpy as np

from herald.config import load_text
from herald.extraction.grounding import default_grounding
from herald.models.stt import WhisperSTT
from herald.models.stt_gates import ClipSignals
from scripts import asr_layer
from scripts.cabin_noise import SR, mix

CFG = asr_layer.cfg()
PROMPT = load_text("prompts/stt_prompt.txt")


def _verdict(said: str, heard: str, facts: list):
    it = {"raw_text": said, "said": said, "whisper": heard}
    ref, hyp = asr_layer.tokens(said), asr_layer.tokens(heard)
    wer = asr_layer.align(ref, hyp)[0] / len(ref)
    return asr_layer.verdict(it, facts, default_grounding(), CFG, PROMPT, wer)


def test_a_misheard_drug_name_is_kept_but_a_lost_number_is_dropped():
    said = "72 year old on apixaban, pulse 92, BP 182 over 104"
    facts = [["patient.age", 72, "m"], ["meds.anticoagulant", "apixaban", "m"], ["vitals.hr", 92, "m"],
             ["vitals.sbp", 182, "m"], ["vitals.dbp", 104, "m"]]
    assert _verdict(said, "72-year-old on a pixaban, pulse 92, BP 182 over 104.", facts) == (True, "kept")
    assert _verdict(said, "72-year-old on apixaban, pulse 9, BP 182 over 104.", facts) == \
        (False, "grounding lost: vitals.hr")
    assert _verdict(said, "Seven-year-old on apixaban, pulse 92, BP 182 over 104.", facts) == \
        (False, "number lost: patient.age")


def test_a_tts_reading_of_iv_as_a_roman_numeral_is_dropped():
    said = "gave 50 of fentanyl IV"
    assert _verdict(said, "Gave 50 of fentanyl roman 4.", [["meds.given", {"drug": "fentanyl", "dose": 50}, "m"]])[1] \
        .startswith("TTS artifact")


def test_prompt_echo_and_repeats_are_dropped():
    said = "she is alert and oriented, no complaints"
    facts = [["vitals.consciousness", "alert", "m"]]
    assert _verdict(said, said + " " + PROMPT[:80], facts)[1] == "prompt echo"
    assert _verdict(said, "she is alert and " * 5, facts)[1].startswith("hallucination")


def test_heard_as_finds_what_whisper_wrote_for_a_drug():
    said = "takes metoprolol and apixaban daily"
    assert asr_layer.heard_as(said, "Takes Metaprolol and a pixaban daily.", "apixaban") == "a pixaban"
    assert asr_layer.heard_as(said, "Takes Metaprolol and a pixaban daily.", "metoprolol") == "metaprolol"


def test_noise_is_mixed_at_the_requested_snr():
    rng = np.random.default_rng(0)
    speech = (0.3 * np.sin(2 * np.pi * 220 * np.arange(SR * 2) / SR)).astype(np.float32)
    clean, parts = mix(speech, None, rng, CFG)
    assert parts == {} and np.allclose(clean[np.abs(clean) > 0], speech[np.abs(speech) > 0])
    for snr in (15, 8, 3):
        y, parts = mix(speech, snr, np.random.default_rng(snr), {**CFG, "siren_share": 1, "beep_share": 1})
        lead = int(np.argmax(np.abs(y) > 0))
        assert parts["siren"] and parts["beeps"]
        # the noise alone before the speech starts sits snr dB under the speech RMS (0.3/sqrt 2)
        pre = y[:int(CFG["lead_seconds"][0] * SR)]
        measured = 20 * np.log10((0.3 / np.sqrt(2)) / np.sqrt(np.mean(pre ** 2)))
        assert abs(measured - snr) < 2.5, (snr, measured, lead)


class _Pipe:
    """Stands in for the transformers pipeline: batched calls take a list, long-form calls one dict."""

    def __init__(self):
        self.calls = []
        self.tokenizer = None

    def __call__(self, x, generate_kwargs, return_timestamps, batch_size=None):
        if isinstance(x, list):
            self.calls.append(("batch", len(x), batch_size))
            return [{"text": f" clip of {len(a['raw']) // 16000} s", "chunks": []} for a in x]
        self.calls.append(("single", len(x["raw"]) // 16000, None))
        return {"text": f" {PROMPT} long clip of {len(x['raw']) // 16000} s", "chunks": []}


def test_transcribe_many_batches_short_clips_and_sends_long_ones_alone_with_the_same_cleanup():
    stt = WhisperSTT("unused")
    stt._pipe = _Pipe()
    stt._signals = lambda clips: [ClipSignals(0.01, "en", 0.99, 0.99) for _ in clips]     # speech: the gates pass
    clips = [np.zeros(16000 * s, np.float32) for s in (3, 40, 5)]
    out = stt.transcribe_many(clips, 16000, batch_size=8)
    assert [o["text"] for o in out] == ["clip of 3 s", "long clip of 40 s", "clip of 5 s"]   # order kept, echo cut
    assert stt._pipe.calls == [("batch", 2, 8), ("single", 40, None)]
    assert [o["seconds"] for o in out] == [3.0, 40.0, 5.0]
