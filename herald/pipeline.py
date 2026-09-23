"""Transcript -> facts. Runs the rules extractor always and the local LLM when
it is being served, then merges. Vitals prefer rules (exact digits); everything
else prefers the LLM when both disagree."""
from __future__ import annotations

import time
from typing import Optional

from . import extract_llm, extract_rules, llm
from .guard import instruction_shaped
from .schema import CapturedBy, FactIn, Role


def merge_llm(rules: list[FactIn], llm_facts: list[FactIn]) -> list[FactIn]:
    """Which model facts to add on top of the rules facts for the same utterance.
    Vitals prefer rules (exact digits). Model-only facts are capped below auto-confirm, so the
    medic confirms them: the bake-off showed the model adds recall but also false facts."""
    by_key = {f.key: f for f in rules}
    out = []
    for f in llm_facts:
        r = by_key.get(f.key)
        if r is None:
            f.confidence = min(f.confidence, 0.8)
            out.append(f)
        elif f.key.startswith("vitals."):
            continue
        elif str(r.value).lower() != str(f.value).lower():
            f.confidence = min(f.confidence, 0.8)
            out.append(f)
    return out


def extract(text: str, captured_by: CapturedBy = CapturedBy.medic, default_role: Role = Role.medic,
            default_speaker: Optional[str] = None, audio_id: Optional[str] = None,
            use_llm: bool = True) -> tuple[list[FactIn], dict]:
    t0 = time.perf_counter()
    rules = extract_rules.extract(text, captured_by, default_role, default_speaker, audio_id)
    info = {"rules": len(rules), "llm": None, "llm_error": None}
    llm_facts: list[FactIn] = []
    info["instruction_shaped"] = instruction_shaped(text)
    if use_llm and llm.available() and not info["instruction_shaped"]:
        try:
            llm_facts = extract_llm.extract(text, captured_by, default_role, default_speaker, audio_id)
            info["llm"] = len(llm_facts)
        except Exception as e:  # the rules result still stands
            info["llm_error"] = str(e)[:200]
    # Same semantics as the app: rules facts stand; the model's additions are appended (merge_llm).
    out = list(rules) + merge_llm(rules, llm_facts)
    info["ms"] = round((time.perf_counter() - t0) * 1000)
    return out, info
