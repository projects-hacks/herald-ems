"""Local speech-to-text: Whisper large-v3-turbo on the GB10 GPU (10.4 s clip -> 0.31 s, 1.7 GiB, measured).
The vocabulary priming prompt is content (config/prompts/stt_prompt.txt)."""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from ..config import load_text
from ..core.ports import UsageRecorder


class WhisperSTT:
    """The `SpeechToText` interface. The model loads on first use (or `warm()`)."""

    def __init__(self, model: str, usage: Optional[UsageRecorder] = None, device: str = "cuda:0"):
        self.model = model
        self.usage = usage
        self.device = device
        self.prompt = load_text("prompts/stt_prompt.txt")
        self._pipe = None
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return self._pipe is not None

    def _load(self):
        with self._lock:
            if self._pipe is None:
                import torch
                from transformers import pipeline
                self._pipe = pipeline("automatic-speech-recognition", model=self.model,
                                      dtype=torch.bfloat16, device=self.device)
        return self._pipe

    def warm(self) -> None:
        self.transcribe(np.zeros(16000, dtype=np.float32), 16000)

    def transcribe(self, audio: np.ndarray, sr: int, language: Optional[str] = None) -> dict:
        pipe = self._load()
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
            kwargs["prompt_ids"] = pipe.tokenizer.get_prompt_ids(self.prompt, return_tensors="pt").to(self.device)
        except Exception:
            pass
        out = pipe({"raw": audio, "sampling_rate": sr}, generate_kwargs=kwargs, return_timestamps=True)
        if self.usage:
            self.usage.record_stt(len(audio) / sr)
        text = out.get("text", "").strip()
        if self.prompt[:30] in text:          # Whisper occasionally echoes the prompt
            text = text.replace(self.prompt, "").strip()
        chunks = [{"text": c["text"].strip(), "t": list(c.get("timestamp") or (None, None))}
                  for c in out.get("chunks", [])]
        return {"text": text, "chunks": chunks, "seconds": round(len(audio) / sr, 2)}
