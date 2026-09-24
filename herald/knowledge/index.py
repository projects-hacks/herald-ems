"""A small BM25 index over sections (pure Python; the corpus is a few hundred sections)."""
from __future__ import annotations

import math
import re
from collections import Counter

from .sections import Section

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")


def _fold(t: str) -> str:
    """Light plural folding so "centers"/"hospitals" match "Center"/"hospital" (no dictionary, no stemmer package)."""
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def tokens(text: str) -> list[str]:
    return [_fold(t) for t in _TOKEN.findall(text.lower())]


class BM25Index:
    def __init__(self, sections: list[Section], k1: float = 1.4, b: float = 0.6):
        self.sections, self.k1, self.b = sections, k1, b
        self.docs = [Counter(tokens(" ".join([*s.parents, s.text]))) for s in sections]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 5) -> list[tuple[float, Section]]:
        q = tokens(query)
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                if t in d:
                    f = d[t]
                    s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg))
            if s > 0:
                scored.append((s, self.sections[i]))
        return sorted(scored, key=lambda x: -x[0])[:k]
