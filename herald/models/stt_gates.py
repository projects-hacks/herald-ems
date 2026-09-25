"""Gates on the speech model's own signals: no speech in the clip, a language Herald does not read (or no clear
language at all), a decode that looped. Thresholds and the language list are content (config/stt.yaml, with their
sources and the measurements behind them). Nothing here touches a model: `WhisperSTT` measures the signals and asks."""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Iterable, Optional

from ..config import load_yaml


def compression_ratio(text: str) -> float:
    """openai-whisper's measure of a repetition loop: UTF-8 bytes over their zlib-compressed size."""
    raw = text.encode("utf-8")
    return len(raw) / len(zlib.compress(raw)) if raw else 0.0


@dataclass(frozen=True)
class ClipSignals:
    """What Whisper's first decoder step says about a clip, before any text is decoded."""
    no_speech_prob: float           # P(<|nospeech|>) over the whole vocabulary
    language: str                   # the most probable language token, as its code ("en", "es", ...)
    language_prob: float            # its probability among the language tokens
    read_prob: float = 1.0          # the probability mass, among the language tokens, on the languages Herald reads


class SpeechGates:
    """Reasons a clip is not read: "no speech", "language", "repetition loop"; None when it passes."""

    def __init__(self, no_speech_threshold: float, compression_ratio_threshold: float, languages: Iterable[str],
                 min_read_language_prob: float = 0.0):
        self.no_speech_threshold = float(no_speech_threshold)
        self.compression_ratio_threshold = float(compression_ratio_threshold)
        self.min_read_language_prob = float(min_read_language_prob)
        self.languages = frozenset(languages)
        if not self.languages:
            raise ValueError("config/stt.yaml gates.languages: at least one language is needed")

    @classmethod
    def from_config(cls, rel: str = "stt.yaml") -> "SpeechGates":
        g = load_yaml(rel)["gates"]
        return cls(g["no_speech_threshold"], g["compression_ratio_threshold"], g["languages"],
                   g.get("min_read_language_prob", 0.0))

    def before_decoding(self, signals: ClipSignals) -> Optional[str]:
        if signals.no_speech_prob > self.no_speech_threshold:
            return "no speech"
        if signals.language not in self.languages or signals.read_prob < self.min_read_language_prob:
            return "language"
        return None

    def after_decoding(self, ratio: float) -> Optional[str]:
        return "repetition loop" if ratio > self.compression_ratio_threshold else None
