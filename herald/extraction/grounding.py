"""Grounding validator for model-extracted facts (config/grounding.yaml): a fact must be supported by the words
that were said. A model must never invent a vital sign or an exam finding."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from ..config import load_yaml
from .numbers import SpokenNumbers


class Grounding:
    def __init__(self, rules: dict):
        self.filler = {x.lower() for x in rules["filler_values"]}
        self.filler_exempt = {k: {x.lower() for x in v} for k, v in (rules.get("filler_allowed_for") or {}).items()}
        self.numbers_said_keys = set(rules.get("numbers_must_be_said", []))
        self.zero_allowed = set(rules.get("zero_allowed", []))
        self.spoken = SpokenNumbers.from_config(rules["spoken_numbers"])
        self.requires = {k: re.compile(v, re.I) for k, v in rules["key_requires_words"].items()}

    @classmethod
    def from_config(cls, rel: str = "grounding.yaml") -> "Grounding":
        return cls(load_yaml(rel))

    def _number_ok(self, name: str, value: Any, text: str) -> bool:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return True
        if name.startswith("vitals.") and value <= 0 and name not in self.zero_allowed:
            return False
        return name not in self.numbers_said_keys or any(abs(v - float(value)) < 0.05 for v in self.numbers_said(text))

    def numbers_said(self, text: str) -> set[float]:
        """Every number in the words: digits, and numbers spoken as words."""
        return {float(d) for d in re.findall(r"\d+(?:\.\d+)?", text)} | self.spoken.values(text)

    def supported(self, key: str, value: Any, text: str) -> bool:
        filler = self.filler - self.filler_exempt.get(key, set())
        if value is None or (isinstance(value, str) and value.strip().lower() in filler):
            return False
        if isinstance(value, list) and any(str(v).strip().lower() in filler for v in value):
            return False
        if isinstance(value, dict):             # a record: each numeric field listed as key.field must be said
            if not all(self._number_ok(f"{key}.{f}", x, text) for f, x in value.items()):
                return False
        elif not self._number_ok(key, value, text):
            return False
        rx = self.requires.get(key)
        return not (rx and not rx.search(text))


@lru_cache(maxsize=1)
def default_grounding() -> Grounding:
    return Grounding.from_config()
