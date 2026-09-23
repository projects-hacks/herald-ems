"""Prompt-injection containment for spoken input.

Anything a patient, family member, or bystander says reaches the extractor, so speech is an
injection surface. Facts describe the patient; instructions ("set SpO2 to 100", "ignore the rules",
"output this JSON") do not. This deterministic detector finds instruction-shaped speech:
- the rules extractor skips instruction-shaped clauses;
- if an utterance contains any, the model's output for that utterance is discarded entirely (the model
  is the component that can be steered), and the trace records why.
Defense in depth: facts from other speakers and code status still require the medic's confirmation.
Measured by eval/adversarial_bench.py (task M9).
"""
from __future__ import annotations

import re
from typing import Optional

INSTRUCTION = re.compile(
    r"\b("
    r"ignore (?:all |the |your |that|this|those)?(?:previous |prior |above )?(?:instructions?|rules|prompt|that|this)?"
    r"|system(?: override)?\s*:|assistant\s*:|user\s*:|override"
    r"|output (?:this|exactly|the following)|return (?:this|exactly) json|pretend (?:you|to)"
    r"|repeat your (?:system )?prompt|list every key|forget (?:the|your|all)"
    r"|(?:set|change|update) (?:the |her |his )?[a-z0-9 ]{2,20}? to\b"
    r"|mark (?:every|all|it|them|this|that|[a-z ]{2,30}? as)"
    r"|write (?:in|into|on) (?:the )?chart|delete (?:the |that|this)|remove (?:the |that|this)"
    r"|add (?:a )?dnr|so the alarm stops|just put|put down|don't bother checking"
    r")", re.I)


def instruction_shaped(text: str) -> Optional[str]:
    """Return the matched instruction phrase, or None if the text only describes."""
    m = INSTRUCTION.search(text)
    return m.group(0).strip() if m else None
