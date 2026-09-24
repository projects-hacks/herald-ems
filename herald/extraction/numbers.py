"""Numbers said in words -> every value they can mean: "one sixty" 160, "one forty two" 142, "one oh two" 102,
"a hundred and ten" 110, "four thousand" 4000, "ninety eight" 98, "thirty seven point one" 37.1. Grounding uses it to check that a
number the model wrote was actually said. The word tables are content (config/grounding.yaml)."""
from __future__ import annotations

import re
from typing import Optional


class SpokenNumbers:
    def __init__(self, units: dict[str, int], teens: dict[str, int], tens: dict[str, int], hundred: list[str],
                 point: list[str], joiners: list[str], one_words: list[str], thousand: list[str] = ()):
        self.units, self.teens, self.tens = units, teens, tens
        self.hundred, self.point, self.joiners, self.one_words = set(hundred), set(point), set(joiners), set(one_words)
        self.thousand = set(thousand)
        self.vocab = set(units) | set(teens) | set(tens) | self.hundred | self.point | self.thousand
        self.max_span = 7

    @classmethod
    def from_config(cls, c: dict) -> "SpokenNumbers":
        return cls(c["units"], c["teens"], c["tens"], c["hundred"], c["point"], c["joiners"], c["one"],
                   c.get("thousand", []))

    def values(self, text: str) -> set[float]:
        """All values any run of number words in `text` can mean (a support check, so every reading counts)."""
        words = re.findall(r"[a-z]+", text.lower())
        out: set[float] = set()
        for run in self._runs(words):
            for i in range(len(run)):
                for j in range(i + 1, min(len(run), i + self.max_span) + 1):
                    out |= self._readings(run[i:j])
        return out

    def spans(self, text: str) -> list[tuple[int, set[float]]]:
        """(character offset, values) for each run of number words, e.g. where "one sixty" starts and {160, ...}."""
        words = [(m.start(), m.group(0)) for m in re.finditer(r"[a-z]+", text.lower())]
        out, k = [], 0
        for run in self._runs([w for _, w in words]):
            while words[k][1] != run[0]:
                k += 1
            vals: set[float] = set()
            for i in range(len(run)):
                for j in range(i + 1, min(len(run), i + self.max_span) + 1):
                    vals |= self._readings(run[i:j])
            out.append((words[k][0], vals))
            k += len(run)
        return out

    def _runs(self, words: list[str]) -> list[list[str]]:
        runs, cur = [], []
        for k, w in enumerate(words):
            nxt = words[k + 1] if k + 1 < len(words) else ""
            if w in self.vocab or (w in self.joiners and cur and nxt in self.vocab) or \
                    (w in self.one_words and (nxt in self.hundred or nxt in self.thousand)):
                cur.append(w)
            elif cur:
                runs.append(cur)
                cur = []
        return runs + ([cur] if cur else [])

    def _readings(self, toks: list[str]) -> set[float]:
        if toks[0] in self.joiners or toks[-1] in self.joiners:
            return set()
        hits = [k for k, t in enumerate(toks) if t in self.point]
        if hits:
            k = hits[0]
            left, right = toks[:k], toks[k + 1:]
            if not right or not all(t in self.units for t in right):
                return set()
            frac = "".join(str(self.units[t]) for t in right)
            return {float(f"{int(v)}.{frac}") for v in (self._readings(left) if left else {0.0}) if v == int(v)}
        return {v for v in (self._arithmetic(toks), self._grouped(toks)) if v is not None}

    def _below_100(self, toks: list[str]) -> Optional[int]:
        if len(toks) == 1:
            t = toks[0]
            return self.units.get(t, self.teens.get(t, self.tens.get(t)))
        if len(toks) == 2 and toks[0] in self.tens and self.units.get(toks[1], 0) > 0:
            return self.tens[toks[0]] + self.units[toks[1]]
        return None

    def _arithmetic(self, toks: list[str]) -> Optional[float]:
        """Standard reading: [n thousand] [and] [one|a] hundred [and] [below 100]."""
        k = next((i for i, t in enumerate(toks) if t in self.thousand), None)
        if k is not None:
            left = self._arithmetic(toks[:k]) if k else None
            if toks[:k] and all(t in self.one_words for t in toks[:k]):
                left = 1.0
            rest = [t for t in toks[k + 1:] if t not in self.joiners]
            right = self._arithmetic(rest) if rest else 0.0
            return None if left is None or right is None or right >= 1000 else left * 1000 + right
        toks = [t for t in toks if t not in self.joiners or t in self.one_words]
        if len(toks) >= 2 and toks[1] in self.hundred and (toks[0] in self.units or toks[0] in self.one_words):
            base = 100 * self.units.get(toks[0], 1)
            rest = [t for t in toks[2:] if t not in self.joiners]
            if not rest:
                return float(base)
            r = self._below_100(rest)
            return float(base + r) if r is not None else None
        r = self._below_100([t for t in toks if t not in self.joiners])
        return float(r) if r is not None else None

    def _grouped(self, toks: list[str]) -> Optional[float]:
        """Digit-group reading, as vitals and times are spoken: "one sixty" 160, "one oh two" 102."""
        if len(toks) < 2 or any(t in self.hundred or t in self.thousand or t in self.joiners for t in toks):
            return None
        s, k = "", 0
        while k < len(toks):
            t = toks[k]
            if t in self.tens and k + 1 < len(toks) and self.units.get(toks[k + 1], 0) > 0:
                s += str(self.tens[t] + self.units[toks[k + 1]])
                k += 2
            elif t in self.tens or t in self.teens or t in self.units:
                s += str(self.tens.get(t, self.teens.get(t, self.units.get(t))))
                k += 1
            else:
                return None
        return float(s)
