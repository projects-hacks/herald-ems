"""Test doubles for the ports in herald/core/ports.py, injected through herald.api.build_context."""
from __future__ import annotations

from typing import Optional

from fastapi.testclient import TestClient

from herald.api import build_context, create_app
from herald.config import Settings


class FakeModel:
    """A TextModel that returns canned rows (or fails), with the usage a real server would report."""

    def __init__(self, name: Optional[str] = "test-model", rows: Optional[list] = None, fail: bool = False):
        self.name, self.rows, self.fail = name, rows or [], fail
        self.calls = 0

    def available(self) -> bool:
        return self.name is not None

    def model_name(self) -> Optional[str]:
        return self.name

    def chat_json(self, system, user, *, image_b64=None, max_tokens=256, schema=None, usage=None, examples=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model down")
        if usage is not None:
            usage.update({"completion_tokens": 42, "prompt_tokens": 100})
        return {"f": self.rows}


class FakeSTT:
    model = "fake-stt"

    def ready(self) -> bool:
        return True

    def transcribe(self, audio, sr, language=None) -> dict:
        return {"text": "", "chunks": [], "seconds": round(len(audio) / sr, 2)}


class FakeVision:
    modes = ("monitor", "pill_bottle", "form", "scene")

    def __init__(self, fail: bool = False, facts: Optional[list] = None):
        self.fail, self.facts = fail, facts or []

    def read(self, image_bytes, mode, photo_id=None):
        if self.fail:
            raise RuntimeError("vision model unavailable")
        return list(self.facts)


def test_settings(**overrides) -> Settings:
    base = Settings.from_env({})          # never the developer's environment
    return base.model_copy(update={"warm_stt": False, **overrides})


def make_client(model: Optional[FakeModel] = None, vision: Optional[FakeVision] = None,
                vision_model: Optional[FakeModel] = None, **settings):
    ctx = build_context(test_settings(**settings), text_model=model or FakeModel(name=None),
                        vision_model=vision_model, stt=FakeSTT(), vision=vision or FakeVision())
    return TestClient(create_app(ctx)), ctx
