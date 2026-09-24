"""Test doubles for the ports in herald/core/ports.py, injected through herald.api.build_context."""
from __future__ import annotations

from typing import Optional

from fastapi.testclient import TestClient

from herald.api import build_context, create_app
from herald.config import Settings
from herald.core.vocabulary import default_vocabulary
from herald.extraction import RulesExtractor
from herald.terminology import MedicationCoder, RxNormNormalizer

# A tiny RxNorm index with real RxCUIs (release 2026-09-08): generic -> itself, brand and salt names -> generic.
TINY_INGREDIENTS = {"11289": "warfarin", "1364430": "apixaban", "1114195": "rivaroxaban", "67108": "enoxaparin",
                    "5224": "heparin", "1037042": "dabigatran etexilate", "32968": "clopidogrel",
                    "83367": "atorvastatin", "1191": "aspirin", "6809": "metformin", "29046": "lisinopril",
                    "10582": "levothyroxine", "161": "acetaminophen", "7804": "oxycodone", "86009": "insulin lispro",
                    "274783": "insulin glargine", "5924": "inulin", "2670": "codeine", "6918": "metoprolol",
                    "7980": "penicillin g"}
TINY_BRANDS = {"coumadin": "11289", "jantoven": "11289", "warfarin sodium": "11289", "eliquis": "1364430",
               "xarelto": "1114195", "lovenox": "67108", "pradaxa": "1037042", "plavix": "32968", "lipitor": "83367",
               "synthroid": "10582", "humalog": "86009", "lantus": "274783", "metoprolol succinate": "6918",
               "percocet": "161+7804"}


def tiny_normalizer() -> RxNormNormalizer:
    names = {n: [c] for c, n in TINY_INGREDIENTS.items()} | {n: [c] for n, c in TINY_BRANDS.items()}
    short = list(names)
    names["warfarin sodium 5 mg oral tablet"] = ["11289"]          # a clinical-drug name: exact match only
    return RxNormNormalizer(TINY_INGREDIENTS, names, short, {"161+7804": "214183"}, release="test")


def tiny_coder() -> MedicationCoder:
    return MedicationCoder.from_config(tiny_normalizer(), default_vocabulary())


def rules_extractor() -> RulesExtractor:
    """The rules extractor as the app wires it, over the tiny index."""
    coder = tiny_coder()
    return RulesExtractor(anticoagulant_names=coder.anticoagulant_names(), coder=coder)


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
    return base.model_copy(update={"warm_stt": False, "knowledge": False, "terminology": False, **overrides})


def make_client(model: Optional[FakeModel] = None, vision: Optional[FakeVision] = None,
                vision_model: Optional[FakeModel] = None, **settings):
    ctx = build_context(test_settings(**settings), text_model=model or FakeModel(name=None),
                        vision_model=vision_model, stt=FakeSTT(), vision=vision or FakeVision(),
                        normalizer=tiny_normalizer())
    return TestClient(create_app(ctx)), ctx
