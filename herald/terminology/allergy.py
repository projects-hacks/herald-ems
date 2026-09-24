"""Allergies to a class of drugs -> NEMSIS eHistory.06's ICD-10-CM codes (config/terminology/allergy_classes.yaml).

Used only for allergens RxNorm leaves unresolved ("sulfa", "penicillin"). A class's names are its NEMSIS label and
the substance in its ICD-10-CM description ("Allergy status to sulfonamides status" -> "sulfonamides"). A name
matches exactly or as its leading word(s) ("sulfa" -> "sulfa drugs"); otherwise by spelling ("penicillins"), which
the coder holds for a tap. Catch-all classes (`exact_only`) must be named exactly. The value stays as said: a class
code annotates the allergy, it doesn't name one substance.
"""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz, process

from ..config import load_yaml
from ..core.schema import NormalizedValue

_STATUS = re.compile(r"^allergy status to\s+|\s+status$")


def _names(c: dict) -> list[str]:
    substance = _STATUS.sub("", c["description"].casefold()).strip()
    substance = re.sub(r"^(other|unspecified)\s+", "", substance)
    return list(dict.fromkeys([" ".join(c["label"].casefold().replace(",", " ").split()), substance]))


class AllergyClasses:
    """A `Normalizer` over the NEMSIS drug-class allergy list."""
    release = "NEMSIS eHistory.06"

    def __init__(self, classes: list[dict], fuzzy_min_ratio: float = 90):
        self.fuzzy_min = fuzzy_min_ratio
        self.by_name: dict[str, dict] = {}
        self.loose: dict[str, dict] = {}                    # names that may match by leading words or spelling
        for c in classes:
            for n in _names(c):
                self.by_name[n] = c
                if not c.get("exact_only"):
                    self.loose[n] = c

    @classmethod
    def from_config(cls, rel: str, fuzzy_min_ratio: float = 90) -> "AllergyClasses":
        return cls(load_yaml(rel)["classes"], fuzzy_min_ratio)

    def normalize(self, key: str, value: str) -> NormalizedValue:
        said = " ".join(str(value).split())
        q = said.casefold().strip(" .,;:!?")
        if q in self.by_name:
            return self._result(said, [self.by_name[q]], "class", 100.0)
        leading = {id(c): c for n, c in self.loose.items() if n.split()[: len(q.split())] == q.split() and q}
        if len(leading) == 1:
            return self._result(said, list(leading.values()), "class", 100.0)
        hits = process.extract(q, list(self.loose), scorer=fuzz.ratio, score_cutoff=self.fuzzy_min, limit=5)
        found = {id(self.loose[n]): self.loose[n] for n, _, _ in hits}
        if len(found) == 1:
            return self._result(said, list(found.values()), "class_fuzzy", max(s for _, s, _ in hits))
        return NormalizedValue(said, None, 0.0, "ambiguous" if found else "unresolved", system="icd10cm")

    @staticmethod
    def _result(said: str, classes: list[dict], method: str, score: float) -> NormalizedValue:
        c = classes[0]
        return NormalizedValue(said, c["code"], round(score, 1), method, (c["label"],), system="icd10cm")
