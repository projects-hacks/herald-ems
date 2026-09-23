"""Rules first (instant), then the local model's additions, merged with the app's semantics."""
from __future__ import annotations

import time
from typing import Optional

from ..core.ports import Extractor
from ..core.schema import CapturedBy, FactIn, Role
from .guard import InstructionGuard, default_guard

MODEL_ONLY_CONFIDENCE_CAP = 0.8   # below auto-confirm: the medic confirms what only the model heard


def merge_model_facts(rules: list[FactIn], model_facts: list[FactIn]) -> list[FactIn]:
    """Which model facts to add on top of the rules facts for the same utterance. Vitals keep the rules value
    (exact digits). Model-only facts, and model values that differ from rules, are capped below auto-confirm."""
    by_key = {f.key: f for f in rules}
    out = []
    for f in model_facts:
        r = by_key.get(f.key)
        if r is None:
            f.confidence = min(f.confidence, MODEL_ONLY_CONFIDENCE_CAP)
            out.append(f)
        elif f.key.startswith("vitals."):
            continue
        elif str(r.value).lower() != str(f.value).lower():
            f.confidence = min(f.confidence, MODEL_ONLY_CONFIDENCE_CAP)
            out.append(f)
    return out


class ExtractionPipeline:
    """The `Extractor` interface over rules + an optional model extractor, with injection containment."""
    name = "pipeline"

    def __init__(self, rules: Extractor, model: Optional[Extractor] = None, guard: Optional[InstructionGuard] = None,
                 model_available=lambda: True):
        self.rules, self.model = rules, model
        self.guard = guard or default_guard()
        self.model_available = model_available

    def run(self, text: str, captured_by: CapturedBy = CapturedBy.medic, default_role: Role = Role.medic,
            default_speaker: Optional[str] = None, audio_id: Optional[str] = None,
            use_model: bool = True) -> tuple[list[FactIn], dict]:
        t0 = time.perf_counter()
        rules = self.rules.extract(text, captured_by, default_role, default_speaker, audio_id)
        info = {"rules": len(rules), "llm": None, "llm_error": None, "instruction_shaped": self.guard.match(text)}
        model_facts: list[FactIn] = []
        if use_model and self.model and self.model_available() and not info["instruction_shaped"]:
            try:
                model_facts = self.model.extract(text, captured_by, default_role, default_speaker, audio_id)
                info["llm"] = len(model_facts)
            except Exception as e:  # the rules result still stands
                info["llm_error"] = str(e)[:200]
        info["ms"] = round((time.perf_counter() - t0) * 1000)
        return list(rules) + merge_model_facts(rules, model_facts), info

    def extract(self, text: str, captured_by: CapturedBy = CapturedBy.medic, default_role: Role = Role.medic,
                default_speaker: Optional[str] = None, audio_id: Optional[str] = None) -> list[FactIn]:
        return self.run(text, captured_by, default_role, default_speaker, audio_id)[0]
