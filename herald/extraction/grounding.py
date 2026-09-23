"""Grounding validator for model-extracted facts (config/grounding.yaml): a fact must be supported by the words
that were said. A model must never invent a vital sign or an exam finding."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from ..config import load_yaml


class Grounding:
    def __init__(self, rules: dict):
        self.filler = {x.lower() for x in rules["filler_values"]}
        self.digits_required = rules.get("vitals_digits_must_appear", True)
        self.digits_exempt = set(rules.get("vitals_digits_exempt", []))
        self.requires = {k: re.compile(v, re.I) for k, v in rules["key_requires_words"].items()}

    @classmethod
    def from_config(cls, rel: str = "grounding.yaml") -> "Grounding":
        return cls(load_yaml(rel))

    def supported(self, key: str, value: Any, text: str) -> bool:
        if value is None or (isinstance(value, str) and value.strip().lower() in self.filler):
            return False
        if isinstance(value, list) and any(str(v).strip().lower() in self.filler for v in value):
            return False
        if key.startswith("vitals.") and isinstance(value, (int, float)) and not isinstance(value, bool):
            if value <= 0:
                return False
            digits = re.findall(r"\d+(?:\.\d+)?", text)
            # spoken-number utterances have no digits; trust the model there
            if self.digits_required and digits and key not in self.digits_exempt:
                if not any(abs(float(d) - float(value)) < 0.05 for d in digits):
                    return False
        rx = self.requires.get(key)
        return not (rx and not rx.search(text))


@lru_cache(maxsize=1)
def default_grounding() -> Grounding:
    return Grounding.from_config()
