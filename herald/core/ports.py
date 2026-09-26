"""Interfaces between Herald's parts (dependency inversion). Concrete classes live in their own packages and are
wired together once, in herald/api/app.py."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Iterator, Optional, Protocol, runtime_checkable

import numpy as np

from .schema import CapturedBy, FactIn, NormalizedValue, Role

if TYPE_CHECKING:
    from ..capture.types import Frame, IncidentEvent


class FrameSource(Protocol):
    def frames(self) -> Iterator[Frame]: ...
    def close(self) -> None: ...


class IncidentListener(Protocol):
    def on_change(self, event: IncidentEvent) -> None: ...


@runtime_checkable
class Extractor(Protocol):
    """Speech text -> candidate facts (rules, a local model, or a pipeline of both)."""
    name: str

    def extract(self, text: str, captured_by: CapturedBy, default_role: Role,
                default_speaker: Optional[str] = None, audio_id: Optional[str] = None) -> list[FactIn]: ...


@runtime_checkable
class Scale(Protocol):
    """A published score or screen computed from confirmed values. Never a prediction, never advice.
    `county` is None for a published score, or the county whose own criteria it encodes (shown only there)."""
    id: str
    name: str
    county: Optional[str]

    def evaluate(self, values: dict[str, Any]) -> dict: ...

    def input_keys(self) -> set[str]: ...

    def relay_text(self, result: dict) -> Optional[str]: ...


class TextModel(Protocol):
    """A local, OpenAI-compatible chat model that returns one JSON object."""
    def available(self) -> bool: ...
    def model_name(self) -> Optional[str]: ...
    def chat_json(self, system: str, user: str, *, image_b64: Optional[str] = None, max_tokens: int = 256,
                  schema: Optional[dict] = None, usage: Optional[dict] = None,
                  examples: Optional[list[tuple[str, str]]] = None) -> dict: ...


class SpeechToText(Protocol):
    model: str
    def ready(self) -> bool: ...
    def transcribe(self, audio: np.ndarray, sr: int, language: Optional[str] = None) -> dict: ...


class PhotoReader(Protocol):
    modes: tuple[str, ...]
    def read(self, image_bytes: bytes, mode: str, photo_id: Optional[str] = None) -> list[FactIn]: ...


class Normalizer(Protocol):
    """One drug or allergen name -> its standard name and code. Never guesses: no match is unresolved."""
    release: str
    def normalize(self, key: str, value: str) -> NormalizedValue: ...


class FactCoder(Protocol):
    """Normalizes the drug and allergen values of a batch of facts (and derives what follows from the codes)."""
    def code(self, facts: list[FactIn]) -> list[FactIn]: ...


class Embedder(Protocol):
    """Text -> L2-normalized vectors for semantic retrieval."""
    def embed(self, texts: list[str], query: bool = False) -> np.ndarray: ...


class Transport(Protocol):
    """Sends one relay packet and returns the receiver's acknowledgement."""
    def __call__(self, wire: bytes) -> Awaitable[dict]: ...


class UsageRecorder(Protocol):
    def record_llm(self, usage: dict, kind: str = "text") -> None: ...
    def record_stt(self, audio_seconds: float) -> None: ...
    def record_stt_dropped(self, reason: str) -> None: ...
