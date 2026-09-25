#!/usr/bin/env python3
"""Speak the measured-ASR sample with Piper TTS (MODEL_PLAN §0k "Measured ASR noise").

Runs in its own venv (Piper is not in the zgx env; never install it there):
  ~/miniforge3/envs/zgx/bin/python -m venv ~/.venvs/piper && ~/.venvs/piper/bin/pip install piper-tts
  ~/.venvs/piper/bin/python scripts/asr_tts.py --plan <plan.jsonl> --voices ~/.cache/piper-voices --out <wav dir>

Each plan line is {"clip", "said", "voice", "length_scale"} (written by `scripts/asr_layer.py plan`); each clip is
written as <out>/<clip>.wav, 16-bit mono at the voice's own rate (22.05 kHz for the medium voices)."""
import argparse
import json
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_voices: dict = {}


def _speak(job: tuple) -> str:
    import numpy as np
    from piper import PiperVoice, SynthesisConfig
    item, vdir, out = job
    path = Path(out) / f"{item['clip']}.wav"
    if path.exists():
        return item["clip"]
    v = _voices.get(item["voice"])
    if v is None:
        v = _voices[item["voice"]] = PiperVoice.load(str(Path(vdir) / f"{item['voice']}.onnx"))
    audio = np.concatenate([c.audio_int16_array for c in
                            v.synthesize(item["said"], SynthesisConfig(length_scale=item["length_scale"]))])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(v.config.sample_rate)
        w.writeframes(audio.tobytes())
    return item["clip"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--voices", required=True, help="folder with <voice>.onnx and <voice>.onnx.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in open(a.plan)]
    items.sort(key=lambda x: x["voice"])           # one voice per worker stretch keeps loads few
    with ProcessPoolExecutor(a.workers) as ex:
        n = sum(1 for _ in ex.map(_speak, [(i, a.voices, a.out) for i in items], chunksize=8))
    print(json.dumps({"spoken": n}))


if __name__ == "__main__":
    main()
