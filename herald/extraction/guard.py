"""Prompt-injection containment for spoken input (patterns in config/guard.yaml).

Anything a patient, family member, or bystander says reaches the extractor, so speech is an injection surface.
Facts describe the patient; instructions ("set SpO2 to 100", "output this JSON") do not. When an utterance
contains instruction-shaped speech, the model still reads it (the team lead's decision, guard_policy=unconfirm),
but every fact from that utterance is held for the medic's tap with a visible reason (`provenance.hold_reason`);
guard_policy=skip_model skips the model instead. The trace records the phrase. Measured by eval/adversarial_bench.py.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from ..config import load_yaml


class InstructionGuard:
    def __init__(self, patterns: list[str]):
        self.patterns = [re.compile(p, re.I) for p in patterns]

    @classmethod
    def from_config(cls, rel: str = "guard.yaml") -> "InstructionGuard":
        return cls(load_yaml(rel)["instruction_patterns"])

    def match(self, text: str) -> Optional[str]:
        """The matched instruction phrase, or None if the text only describes."""
        for rx in self.patterns:
            if m := rx.search(text):
                return m.group(0).strip()
        return None


@lru_cache(maxsize=1)
def default_guard() -> InstructionGuard:
    return InstructionGuard.from_config()


def instruction_shaped(text: str) -> Optional[str]:
    return default_guard().match(text)
