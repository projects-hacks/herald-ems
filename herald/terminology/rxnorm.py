"""Drug and allergen names -> RxNorm ingredients, from the local index (scripts/build_rxnorm_index.py).

Matching stops at the first hit (thresholds and word lists: config/terminology.yaml):
1. exact: the name, then the name without a trailing strength that has a unit ("warfarin 5 mg");
2. exact product name: a branded product said with its number ("Tylenol 3" -> acetaminophen / codeine);
   a number left after that means the name is a product we don't know: nothing looser is tried;
3. combination: every part of "ipratropium-albuterol" is exact and together they are an RxNorm multi-ingredient;
4. a phrase made only of words RxNorm uses ("insulin", "nitro spray") is never read as a misspelling. For the keys
   that allow it, it may resolve to the one ingredient every single-ingredient product with those words shares
   ("nitro spray" -> nitroglycerin; "insulin" has many, so it stays unresolved);
5. otherwise fuzzy (rapidfuzz ratio), then phonetic (Metaphone, a single ingredient, a spelling floor).
A candidate more specific than what was said ("penicillin" -> "penicillin g") is never taken, and anything
unmatched or ambiguous keeps the spoken text, unresolved. Only exact matches are certain; the coder holds the rest
for the medic's tap.
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

_WORD = re.compile(r"[a-z0-9]+")
_DIGIT = re.compile(r"\d")


def strength_tail(name: str, units: Iterable[str]) -> str:
    """`name` without trailing strengths that carry a unit ("warfarin 5 mg", "x 300 mg / 30 mg"); other numbers
    stay, because they may be part of the product's name ("tylenol 3", "humalog mix 75/25")."""
    unit = "|".join(sorted((re.escape(u) for u in units), key=len, reverse=True))
    tail = re.compile(rf"\s*/?\s+\d[\d.,]*\s*(?:{unit})(?:\s*/\s*\d*[\d.,]*\s*(?:{unit}))?\s*$")
    prev = None
    while prev != name:
        prev, name = name, tail.sub("", name)
    return name.strip()


def _narrows(said: str, name: str) -> bool:
    return set(said.split()) < set(name.split())


class RxNormNormalizer:
    """The `Normalizer` interface over an in-memory RxNorm index."""

    def __init__(self, ingredients: dict[str, str], names: dict[str, list[str]], short: Iterable[str],
                 multi: Optional[dict[str, str]] = None, *, heads: Optional[dict[str, str]] = None,
                 supplement: Optional[dict[str, str]] = None, supplement_fuzzy: bool = True, release: str = "",
                 min_length: int = 5, fuzzy_min_ratio: float = 90, phonetic_min_similarity: float = 0.6,
                 strength_units: Iterable[str] = ("mg", "mcg", "g", "ml", "unt", "units", "%"),
                 combination_separators: Iterable[str] = ("-", "/", "+", "&", " and ", " with "),
                 contained_keys: Iterable[str] = ()):
        supplement = supplement or {}
        self.ingredients, self.multi, self.heads = ingredients, multi or {}, heads or {}
        self.names = {**{n: [k] for n, k in supplement.items() if n not in names}, **names}
        self.release = release
        self.min_length, self.fuzzy_min, self.phonetic_min = min_length, fuzzy_min_ratio, phonetic_min_similarity
        self.units = tuple(strength_units)
        # " and " -> a word between spaces; "-" -> the character itself
        self._split = re.compile("|".join(rf"\s+{re.escape(sep.strip())}\s+" if sep != sep.strip() else re.escape(sep)
                                          for sep in combination_separators if sep.strip()))
        self.contained_keys = set(contained_keys)
        short = set(short) | (set(supplement) if supplement_fuzzy else set())
        self._short = sorted(n for n in short if len(n) >= min_length)
        # Words that occur in RxNorm names ("insulin", "nitro", "penicillin"): said on their own they are real,
        # less specific terms, not misspellings, so they are never fuzzy- or sound-matched to another drug.
        self._words = {w for n in self.names for w in _WORD.findall(n)}
        # word -> ingredient-set keys of the names (with one key) that contain it: for "contained" matching
        self._word_keys: dict[str, set[str]] = defaultdict(set)
        for n, ks in self.names.items():
            if len(ks) == 1:
                for w in set(_WORD.findall(n)):
                    self._word_keys[w].add(ks[0])
        self._sounds: dict[str, list[str]] = defaultdict(list)
        for n in self._short:
            self._sounds[jellyfish.metaphone(n)].append(n)

    @classmethod
    def load(cls, path: Path) -> "RxNormNormalizer":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = load_yaml("terminology.yaml")
        m = cfg["match"]
        return cls(d["ingredients"], d["names"], d["short"], d["multi"], heads=d.get("heads"),
                   supplement=d.get("supplement"), supplement_fuzzy=cfg["rxnav"]["fuzzy"], release=d["release"],
                   min_length=m["min_length"], fuzzy_min_ratio=m["fuzzy_min_ratio"],
                   phonetic_min_similarity=m["phonetic_min_similarity"], strength_units=m["strength_units"],
                   combination_separators=m["combination_separators"], contained_keys=cfg["keys"]["contained"])

    # ---------- the Normalizer interface ----------
    def normalize(self, key: str, value: str) -> NormalizedValue:
        said = " ".join(str(value).split())
        q = said.casefold().strip(" .,;:!?")
        base = strength_tail(q, self.units)
        for name in dict.fromkeys([q, base]):
            if name in self.names:
                return self._result(said, self.names[name], "exact", 100.0)
        head = " ".join(base.replace("#", " ").split())
        if head in self.heads:
            return self._result(said, [self.heads[head]], "exact", 100.0)
        if _DIGIT.search(base):                     # a numbered product we don't know: never approximate it
            return NormalizedValue(said, None, 0.0, "unresolved")
        combo = self._combination(said, base)
        if combo is not None:
            return combo
        words = _WORD.findall(base)
        if words and all(w in self._words for w in words):
            hit = self._contained(said, words) if key in self.contained_keys else None
            return hit or NormalizedValue(said, None, 0.0, "unresolved")
        if len(base) < self.min_length:
            return NormalizedValue(said, None, 0.0, "unresolved")
        return self._fuzzy(said, base) or self._phonetic(said, base) or NormalizedValue(said, None, 0.0, "unresolved")

    # ---------- steps ----------
    def _exact_key(self, part: str) -> Optional[str]:
        keys = self.names.get(strength_tail(part, self.units)) or self.names.get(part)
        return keys[0] if keys and len(keys) == 1 else None

    def _combination(self, said: str, base: str) -> Optional[NormalizedValue]:
        parts = [p.strip() for p in self._split.split(base) if p.strip()]
        if len(parts) < 2:
            return None
        keys = [self._exact_key(p) for p in parts]
        if not all(keys):
            return None
        codes = sorted({c for k in keys for c in k.split("+")}, key=int)
        key = "+".join(codes)
        if key not in self.multi:                  # not a product RxNorm knows: two drugs, not one combination
            return None
        return self._result(said, [key], "combination", 100.0)

    def _contained(self, said: str, words: list[str]) -> Optional[NormalizedValue]:
        keys = set.intersection(*(self._word_keys.get(w, set()) for w in words))
        single = {k for k in keys if "+" not in k}
        pick = single or keys
        return self._result(said, sorted(pick), "contained", 100.0) if len(pick) == 1 else None

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
