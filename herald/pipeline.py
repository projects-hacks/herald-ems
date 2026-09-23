"""Transcript -> facts. Runs the rules extractor always and the local LLM when
it is being served, then merges. Vitals prefer rules (exact digits); everything
else prefers the LLM when both disagree."""
from __future__ import annotations

import time
from typing import Optional

from . import extract_llm, extract_rules, llm
from .schema import CapturedBy, FactIn, Role


def extract(text: str, captured_by: CapturedBy = CapturedBy.medic, default_role: Role = Role.medic,
            default_speaker: Optional[str] = None, audio_id: Optional[str] = None,
            use_llm: bool = True) -> tuple[list[FactIn], dict]:
    t0 = time.perf_counter()
    rules = extract_rules.extract(text, captured_by, default_role, default_speaker, audio_id)
    info = {"rules": len(rules), "llm": None, "llm_error": None}
    llm_facts: list[FactIn] = []
    if use_llm and llm.available():
        try:
            llm_facts = extract_llm.extract(text, captured_by, default_role, default_speaker, audio_id)
            info["llm"] = len(llm_facts)
        except Exception as e:  # the rules result still stands
            info["llm_error"] = str(e)[:200]
    merged: dict[str, FactIn] = {}
    for f in rules:
        merged[f.key] = f
    for f in llm_facts:
        r = merged.get(f.key)
        if r is None:
            # Model-only facts are never auto-confirmed: the bake-off (2026-09-23) showed the model adds
            # recall (number words, corrections) but also false facts. The medic confirms them.
            f.confidence = min(f.confidence, 0.8)
            merged[f.key] = f
        elif f.key.startswith("vitals."):
            continue
        elif str(r.value).lower() == str(f.value).lower():
            r.confidence = max(r.confidence, f.confidence)
            r.provenance.extractor = f"rules+{f.provenance.extractor}"
        else:
            merged[f.key] = f
    info["ms"] = round((time.perf_counter() - t0) * 1000)
    return list(merged.values()), info
