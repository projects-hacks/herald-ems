"""Local speech-to-text: Whisper large-v3-turbo on the GB10 GPU.
Measured on this box: 10.4 s clip -> 0.31 s, 1.7 GiB."""
from __future__ import annotations

import os
import threading
from typing import Optional

import numpy as np

MODEL = os.getenv("HERALD_STT_MODEL", "openai/whisper-large-v3-turbo")
# Priming Whisper with EMS vocabulary improves spelling of drug names and numbers.
PROMPT = ("Paramedic report. BP 182 over 104, pulse 92, SpO2 95 on room air, glucose 142, "
          "last known well 1:40, left facial droop, arm drift, warfarin, Eliquis, Xarelto, RACE, NEWS2.")

_pipe = None
_lock = threading.Lock()


def _load():
    global _pipe
    with _lock:
        if _pipe is None:
            import torch
            from transformers import pipeline
            _pipe = pipeline("automatic-speech-recognition", model=MODEL,
                             torch_dtype=torch.bfloat16, device="cuda:0")
    return _pipe


def warm() -> None:
    transcribe(np.zeros(16000, dtype=np.float32), 16000)


def transcribe(audio: np.ndarray, sr: int, language: Optional[str] = None) -> dict:
    pipe = _load()
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    if sr != 16000:
        import torch
        import torchaudio.functional as AF
        audio = AF.resample(torch.from_numpy(audio), sr, 16000).numpy()
        sr = 16000
    kwargs = {"task": "transcribe"}
    if language:
        kwargs["language"] = language
    try:
        kwargs["prompt_ids"] = pipe.tokenizer.get_prompt_ids(PROMPT, return_tensors="pt").to("cuda:0")
    except Exception:
        pass
    out = pipe({"raw": audio, "sampling_rate": sr}, generate_kwargs=kwargs, return_timestamps=True)
    text = out.get("text", "").strip()
    if PROMPT[:30] in text:          # Whisper occasionally echoes the prompt
        text = text.replace(PROMPT, "").strip()
    chunks = [{"text": c["text"].strip(), "t": list(c.get("timestamp") or (None, None))}
              for c in out.get("chunks", [])]
    return {"text": text, "chunks": chunks, "seconds": round(len(audio) / sr, 2)}
