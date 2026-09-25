"""Local speech-to-text: Whisper large-v3-turbo on the GB10 GPU (10.4 s clip -> 0.31 s, 1.7 GiB, measured).
The vocabulary priming prompt is content (config/prompts/stt_prompt.txt)."""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from ..config import load_text
from ..core.ports import UsageRecorder
from .weights import local_weights


class WhisperSTT:
    """The `SpeechToText` interface. The model loads on first use (or `warm()`)."""

    WINDOW = 30.0                             # seconds in one Whisper input window (batching needs clips within it)

    def __init__(self, model: str, usage: Optional[UsageRecorder] = None, device: str = "cuda:0", offline: bool = True):
        self.model = model
        self.offline = offline
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
                self._pipe = pipeline("automatic-speech-recognition", model=local_weights(self.model, self.offline),
                                      dtype=torch.bfloat16, device=self.device)
        return self._pipe

    def warm(self) -> None:
        self.transcribe(np.zeros(16000, dtype=np.float32), 16000)

    def _kwargs(self, pipe, language: Optional[str]) -> dict:
        kwargs = {"task": "transcribe"}
        if language:
            kwargs["language"] = language
        try:
            kwargs["prompt_ids"] = pipe.tokenizer.get_prompt_ids(self.prompt, return_tensors="pt").to(self.device)
        except Exception:
            pass
        return kwargs

    def _result(self, out: dict, seconds: float) -> dict:
        text = out.get("text", "").strip()
        if self.prompt[:30] in text:          # Whisper occasionally echoes the prompt
            text = text.replace(self.prompt, "").strip()
        chunks = [{"text": c["text"].strip(), "t": list(c.get("timestamp") or (None, None))}
                  for c in out.get("chunks", [])]
        return {"text": text, "chunks": chunks, "seconds": round(seconds, 2)}

    @staticmethod
    def _mono16k(audio: np.ndarray, sr: int) -> np.ndarray:
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)
        if sr != 16000:
            import torch
            import torchaudio.functional as AF
            audio = AF.resample(torch.from_numpy(audio), sr, 16000).numpy()
        return audio

    def transcribe(self, audio: np.ndarray, sr: int, language: Optional[str] = None) -> dict:
        pipe = self._load()
        audio = self._mono16k(audio, sr)
        out = pipe({"raw": audio, "sampling_rate": 16000}, generate_kwargs=self._kwargs(pipe, language),
                   return_timestamps=True)
        if self.usage:
            self.usage.record_stt(len(audio) / 16000)
        return self._result(out, len(audio) / 16000)

    def transcribe_many(self, clips: list[np.ndarray], sr: int, language: Optional[str] = None,
                        batch_size: int = 16) -> list[dict]:
        """`transcribe` for many clips in GPU batches: the same prompt, settings and echo stripping (offline
        measurement and training-data work; the app transcribes one capture at a time)."""
        pipe = self._load()
        audio = [self._mono16k(a, sr) for a in clips]
        short = [i for i, a in enumerate(audio) if len(a) <= self.WINDOW * 16000]     # one Whisper window each
        outs: dict[int, dict] = {}
        if short:
            res = pipe([{"raw": audio[i], "sampling_rate": 16000} for i in short],
                       generate_kwargs=self._kwargs(pipe, language), return_timestamps=True, batch_size=batch_size)
            outs.update(zip(short, res))
        for i in set(range(len(audio))) - set(short):                             # long-form: one at a time
            outs[i] = pipe({"raw": audio[i], "sampling_rate": 16000}, generate_kwargs=self._kwargs(pipe, language),
                           return_timestamps=True)
        if self.usage:
            for a in audio:
                self.usage.record_stt(len(a) / 16000)
        return [self._result(outs[i], len(a) / 16000) for i, a in enumerate(audio)]
