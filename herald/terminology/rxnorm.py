"""Drug and allergen names -> RxNorm ingredients, from the local index (scripts/build_rxnorm_index.py).

Matching stops at the first hit: exact (casefold, then without a trailing strength such as "5 mg") -> fuzzy
(rapidfuzz ratio) -> phonetic (Metaphone, only when a single ingredient fits and the spelling is close enough by
Levenshtein similarity). Thresholds: config/terminology.yaml. A candidate more specific than what
was said ("penicillin" -> "penicillin g", "insulin" -> "insulin lispro") is never taken: that would be a guess.
Nor is a word RxNorm already uses ("insulin" is not a misspelling of "inulin"). Anything unmatched or ambiguous
keeps the spoken text, unresolved.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

import jellyfish
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from ..config import load_yaml
from ..core.schema import NormalizedValue

_DOSE_TAIL = re.compile(r"\s+\d.*$")
_WORD = re.compile(r"[a-z0-9]+")


def _narrows(said: str, name: str) -> bool:
    return set(said.split()) < set(name.split())


class RxNormNormalizer:
    """The `Normalizer` interface over an in-memory RxNorm index."""

    def __init__(self, ingredients: dict[str, str], names: dict[str, list[str]], short: Iterable[str],
                 multi: Optional[dict[str, str]] = None, *, release: str = "", min_length: int = 5,
                 fuzzy_min_ratio: float = 90, phonetic_min_similarity: float = 0.6):
        self.ingredients, self.names, self.multi = ingredients, names, multi or {}
        self.release = release
        self.min_length, self.fuzzy_min, self.phonetic_min = min_length, fuzzy_min_ratio, phonetic_min_similarity
        self._short = sorted(n for n in short if len(n) >= min_length)
        # Words that occur in RxNorm names ("insulin", "nitro", "penicillin"): said on their own they are real,
        # less specific terms, not misspellings, so they are never fuzzy- or sound-matched to another drug.
        self._words = {w for n in names for w in _WORD.findall(n)}
        self._sounds: dict[str, list[str]] = defaultdict(list)
        for n in self._short:
            self._sounds[jellyfish.metaphone(n)].append(n)

    @classmethod
    def load(cls, path: Path) -> "RxNormNormalizer":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["ingredients"], d["names"], d["short"], d["multi"], release=d["release"],
                   **load_yaml("terminology.yaml")["match"])

    def normalize(self, key: str, value: str) -> NormalizedValue:
        said = " ".join(str(value).split())
        q = said.casefold().strip(" .,;:!?")
        base = _DOSE_TAIL.sub("", q)
        for name in dict.fromkeys([q, base]):
            if name in self.names:
                return self._result(said, self.names[name], "exact", 100.0)
        if len(base) < self.min_length or all(w in self._words for w in _WORD.findall(base)):
            return NormalizedValue(said, None, 0.0, "unresolved")
        return self._fuzzy(said, base) or self._phonetic(said, base) or NormalizedValue(said, None, 0.0, "unresolved")

    def names_for(self, ingredients: Iterable[str]) -> dict[str, str]:
        """Every generic and brand name whose only ingredient is one of these -> that ingredient's name."""
        wanted = set(ingredients)
        by_code = {c: n for c, n in self.ingredients.items() if n in wanted}
        return {n: by_code[self.names[n][0]] for n in self._short
                if len(self.names[n]) == 1 and self.names[n][0] in by_code}

    def _fuzzy(self, said: str, base: str) -> Optional[NormalizedValue]:
        hits = [(n, s) for n, s, _ in process.extract(base, self._short, scorer=fuzz.ratio,
                                                      score_cutoff=self.fuzzy_min, limit=20)
                if not _narrows(base, n)]
        if not hits:
            return None
        best = max(s for _, s in hits)
        keys = sorted({k for n, s in hits if s == best for k in self.names[n]})
        return self._result(said, keys, "fuzzy", best)

    def _phonetic(self, said: str, base: str) -> Optional[NormalizedValue]:
        sounds_alike = [n for n in self._sounds.get(jellyfish.metaphone(base), ()) if not _narrows(base, n)]
        hits = [(n, s) for n in sounds_alike if (s := Levenshtein.normalized_similarity(base, n)) >= self.phonetic_min]
        if not hits:
            return None
        keys = sorted({k for n, _ in hits for k in self.names[n]})
        return self._result(said, keys, "phonetic", 100 * max(s for _, s in hits))

    def _result(self, said: str, keys: list[str], method: str, score: float) -> NormalizedValue:
        if len(keys) != 1:
            return NormalizedValue(said, None, round(score, 1), "ambiguous")
        codes = keys[0].split("+")
        names = tuple(sorted(self.ingredients[c] for c in codes))
        code = codes[0] if len(codes) == 1 else self.multi.get(keys[0])
        return NormalizedValue(" / ".join(names), code, round(score, 1), method, names)
