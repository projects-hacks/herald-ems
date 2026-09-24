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
        self.numbers_said_keys = set(rules.get("numbers_must_be_said", []))
        self.spoken = SpokenNumbers.from_config(rules["spoken_numbers"])
        self.requires = {k: re.compile(v, re.I) for k, v in rules["key_requires_words"].items()}

    @classmethod
    def from_config(cls, rel: str = "grounding.yaml") -> "Grounding":
        return cls(load_yaml(rel))

    def numbers_said(self, text: str) -> set[float]:
        """Every number in the words: digits, and numbers spoken as words."""
        return {float(d) for d in re.findall(r"\d+(?:\.\d+)?", text)} | self.spoken.values(text)

    def supported(self, key: str, value: Any, text: str) -> bool:
        if value is None or (isinstance(value, str) and value.strip().lower() in self.filler):
            return False
        if isinstance(value, list) and any(str(v).strip().lower() in self.filler for v in value):
            return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if key.startswith("vitals.") and value <= 0:
                return False
            if key in self.numbers_said_keys and not any(abs(v - float(value)) < 0.05 for v in self.numbers_said(text)):
                return False
        rx = self.requires.get(key)
        return not (rx and not rx.search(text))


@lru_cache(maxsize=1)
def default_grounding() -> Grounding:
    return Grounding.from_config()
