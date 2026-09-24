"""Test doubles for the ports in herald/core/ports.py, injected through herald.api.build_context."""
from __future__ import annotations

from typing import Optional

from fastapi.testclient import TestClient

from herald.api import build_context, create_app
from herald.config import Settings
from herald.core.vocabulary import default_vocabulary
from herald.terminology import MedicationCoder, RxNormNormalizer

# A tiny RxNorm index with real RxCUIs (release 2026-09-08): generics, brands, a few product names, one numbered
# product ("tylenol 3"), combinations, and two brand names from the RxNav supplement (Zofran, Vicodin).
TINY_INGREDIENTS = {"11289": "warfarin", "1364430": "apixaban", "1114195": "rivaroxaban", "67108": "enoxaparin",
                    "5224": "heparin", "1037042": "dabigatran etexilate", "32968": "clopidogrel",
                    "83367": "atorvastatin", "1191": "aspirin", "6809": "metformin", "29046": "lisinopril",
                    "10582": "levothyroxine", "161": "acetaminophen", "7804": "oxycodone", "86009": "insulin lispro",
                    "274783": "insulin glargine", "5924": "inulin", "2670": "codeine", "6918": "metoprolol",
                    "7980": "penicillin g", "7984": "penicillin v", "435": "albuterol", "7213": "ipratropium",
                    "4917": "nitroglycerin", "40254": "valproate", "26225": "ondansetron", "5489": "hydrocodone",
                    "7242": "naloxone", "357977": "sunitinib", "8591": "peanut oil"}
TINY_BRANDS = {"coumadin": "11289", "jantoven": "11289", "warfarin sodium": "11289", "eliquis": "1364430",
               "xarelto": "1114195", "lovenox": "67108", "pradaxa": "1037042", "plavix": "32968", "lipitor": "83367",
               "synthroid": "10582", "humalog": "86009", "lantus": "274783", "metoprolol succinate": "6918",
               "percocet": "161+7804", "tylenol": "161", "narcan": "7242", "sutent": "357977",
               "depakote": "40254", "combivent": "435+7213"}
TINY_PRODUCTS = {                                    # clinical and branded drug names: exact matches, and words
    "warfarin sodium 5 mg oral tablet": "11289", "nitroglycerin 0.4 mg sublingual tablet": "4917",
    "nitro spray pump 0.4 mg/actuat": "4917", "nitro-dur 0.1 mg/hr transdermal system": "4917",
    "divalproex sodium 500 mg delayed release oral tablet": "40254",
    "insulin lispro 100 unt/ml injectable solution": "86009", "insulin glargine 100 unt/ml pen injector": "274783",
    "penicillin v potassium 500 mg oral tablet": "7984", "albuterol 0.09 mg/actuat metered dose inhaler": "435",
    "acetaminophen 300 mg / codeine phosphate 30 mg oral tablet [tylenol with codeine]": "161+2670"}
TINY_MULTI = {"161+7804": "214183", "435+7213": "214199", "161+2670": "817579", "161+5489": "857005"}


def tiny_normalizer() -> RxNormNormalizer:
    short = {n: [c] for c, n in TINY_INGREDIENTS.items()} | {n: [c] for n, c in TINY_BRANDS.items()}
    names = short | {n: [c] for n, c in TINY_PRODUCTS.items()}
    return RxNormNormalizer(TINY_INGREDIENTS, names, list(short), TINY_MULTI, heads={"tylenol 3": "161+2670"},
                            supplement={"zofran": "26225", "vicodin": "161+5489"}, release="test",
                            strength_units=["mg", "mcg", "ml", "unt", "units", "%", "milligrams"],
                            contained_keys=["meds.list", "meds.given", "meds.anticoagulant"])


def tiny_coder() -> MedicationCoder:
    return MedicationCoder.from_config(tiny_normalizer(), default_vocabulary())


class FakeModel:
    """A TextModel that returns canned rows (or fails), with the usage a real server would report."""

    def __init__(self, name: Optional[str] = "test-model", rows: Optional[list] = None, fail: bool = False,
                 conf: float = 0.999):
        self.name, self.rows, self.fail, self.conf = name, rows or [], fail, conf
        self.calls = 0

    def available(self) -> bool:
        return self.name is not None

    def model_name(self) -> Optional[str]:
        return self.name

    def chat_json(self, system, user, *, image_b64=None, max_tokens=256, schema=None, usage=None, examples=None,
                  logprobs=False, top_logprobs=0):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model down")
        if usage is not None:
            usage.update({"completion_tokens": 42, "prompt_tokens": 100})
        out = {"f": self.rows}
        if logprobs:        # one token spanning the output: every row gets confidence `conf`
            import json
            import math
            content = json.dumps(out, separators=(",", ":"))
            out = {**out, "_content": content, "_tokens": [(content, math.log(self.conf))]}
        return out


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
                vision_model: Optional[FakeModel] = None, normalizer=None, **settings):
    """The app over fakes. Drug coding is off unless a normalizer is passed (e.g. `tiny_normalizer()`)."""
    ctx = build_context(test_settings(**settings), text_model=model or FakeModel(name=None),
                        vision_model=vision_model, stt=FakeSTT(), vision=vision or FakeVision(),
                        normalizer=normalizer)
    return TestClient(create_app(ctx)), ctx
