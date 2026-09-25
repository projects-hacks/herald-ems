"""Numbers said in words -> every value they can mean: "one sixty" 160, "one forty two" 142, "one oh two" 102,
"a hundred and ten" 110, "four thousand" 4000, "ninety eight" 98, "thirty seven point one" 37.1, and in Spanish
"ciento ochenta" 180, "noventa y dos" 92, "treinta y siete y medio" 37.5, "mil quinientos" 1500. Grounding uses it to
check that a number the model wrote was actually said. The word tables are language data (config/numbers.yaml)."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional


def fold_accents(text: str) -> str:
    """"veintidós" -> "veintidos", one character for one, so offsets into the original text stay valid."""
    out = []
    for c in text:
        d = unicodedata.normalize("NFD", c)
        out.append(d[0] if len(d) > 1 and all(unicodedata.combining(x) for x in d[1:]) else c)
    return "".join(out)


class SpokenNumbers:
    """The number words of one language."""

    def __init__(self, units: dict[str, int], teens: dict[str, int], tens: dict[str, int], hundred: list[str],
                 point: list[str], joiners: list[str], one_words: list[str], thousand: list[str] = (),
                 hundreds: Optional[dict[str, int]] = None, half: Iterable[str] = (), bare_thousand: bool = False,
                 accents: bool = False, not_alone: Iterable[str] = ()):
        self.accents = accents
        f = fold_accents if accents else (lambda w: w)
        units, teens, tens = ({f(k): v for k, v in t.items()} for t in (units, teens, tens))
        self.units, self.teens, self.tens = units, teens, tens
        self.hundred, self.point, self.joiners, self.one_words = (
            {f(w) for w in ws} for ws in (hundred, point, joiners, one_words))
        self.thousand = {f(w) for w in thousand}
        self.hundreds = {f(k): v for k, v in (hundreds or {}).items()}
        self.half = {f(w) for w in half}
        self.bare_thousand = bare_thousand
        self.not_alone = {f(w) for w in not_alone}   # ordinary words in another language ("once"): need company
        self.vocab = set(units) | set(teens) | set(tens) | self.hundred | self.point | self.thousand | set(self.hundreds)
        self.max_span = 7

    @classmethod
    def from_config(cls, c: dict) -> "SpokenNumbers":
        return cls(c["units"], c["teens"], c["tens"], c.get("hundred", []), c.get("point", []), c.get("joiners", []),
                   c.get("one", []), c.get("thousand", []), hundreds=c.get("hundreds"), half=c.get("half", []),
                   bare_thousand=bool(c.get("bare_thousand", False)), accents=bool(c.get("fold_accents", False)),
                   not_alone=c.get("not_alone", []))

    def _words(self, text: str) -> list[tuple[int, str]]:
        low = text.lower()
        return [(m.start(), m.group(0)) for m in re.finditer(r"[a-z]+", fold_accents(low) if self.accents else low)]

    def values(self, text: str) -> set[float]:
        """All values any run of number words in `text` can mean (a support check, so every reading counts)."""
        out: set[float] = set()
        for _, vals in self.spans(text):
            out |= vals
        return out

    def spans(self, text: str) -> list[tuple[int, set[float]]]:
        """(character offset, values) for each run of number words, e.g. where "one sixty" starts and {160, ...}."""
        words = self._words(text)
        out, k = [], 0
        for run in self._runs([w for _, w in words]):
            # The run's offset is the next place its first word appears. (For a run that starts with a word said
            # earlier too, e.g. "a" in "a hundred", that can be the earlier place; kept as is, because the training-set
            # builder orders facts by these offsets and its output must not change.)
            while words[k][1] != run[0]:
                k += 1
            start, k = words[k][0], k + len(run)
            if self._alone(run):
                continue
            vals: set[float] = set()
            for i in range(len(run)):
                for j in range(i + 1, min(len(run), i + self.max_span) + 1):
                    vals |= self._readings(run[i:j])
            out.append((start, vals))
        return out

    def _alone(self, run: list[str]) -> bool:
        return all(w in self.not_alone for w in run)

    def _runs(self, words: list[str]) -> list[list[str]]:
        runs, cur = [], []
        for k, w in enumerate(words):
            nxt = words[k + 1] if k + 1 < len(words) else ""
            if w in self.vocab or (w in self.joiners and cur and (nxt in self.vocab or nxt in self.half)) or \
                    (w in self.one_words and (nxt in self.hundred or nxt in self.thousand)) or \
                    (w in self.half and cur and cur[-1] in self.joiners):
                cur.append(w)
            elif cur:
                runs.append(cur)
                cur = []
        return runs + ([cur] if cur else [])

    def _readings(self, toks: list[str]) -> set[float]:
        if toks[0] in self.joiners or toks[-1] in self.joiners or toks[0] in self.half:
            return set()
        if toks[-1] in self.half:                      # "treinta y siete y medio": 37.5
            if len(toks) < 3 or toks[-2] not in self.joiners:
                return set()
            return {v + 0.5 for v in self._readings(toks[:-2]) if v == int(v)}
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
        """Standard reading: [n thousand] [and] [one|a] hundred [and] [below 100]; or [hundreds word] [below 100]."""
        k = next((i for i, t in enumerate(toks) if t in self.thousand), None)
        if k is not None:
            left = self._arithmetic(toks[:k]) if k else (1.0 if self.bare_thousand else None)
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
        if toks and toks[0] in self.hundreds:
            rest = [t for t in toks[1:] if t not in self.joiners]
            if not rest:
                return float(self.hundreds[toks[0]])
            r = self._below_100(rest)
            return float(self.hundreds[toks[0]] + r) if r is not None else None
        r = self._below_100([t for t in toks if t not in self.joiners])
        return float(r) if r is not None else None

    def _grouped(self, toks: list[str]) -> Optional[float]:
        """Digit-group reading, as vitals and times are spoken: "one sixty" 160, "one oh two" 102."""
        if len(toks) < 2 or any(t in self.hundred or t in self.thousand or t in self.joiners or t in self.hundreds
                                for t in toks):
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


class SpokenNumberLanguages:
    """Number words in several languages at once (the crew and the people at the scene may speak different ones):
    a number counts as said when any language's words say it. Same interface as `SpokenNumbers`."""

    def __init__(self, languages: dict[str, SpokenNumbers]):
        self.languages = languages

    @classmethod
    def from_config(cls, tables: dict, names: list[str]) -> "SpokenNumberLanguages":
        missing = [n for n in names if n not in tables]
        if missing:
            raise ValueError(f"number words for {missing} are not in config/numbers.yaml")
        return cls({n: SpokenNumbers.from_config(tables[n]) for n in names})

    def values(self, text: str) -> set[float]:
        out: set[float] = set()
        for lang in self.languages.values():
            out |= lang.values(text)
        return out

    def spans(self, text: str) -> list[tuple[int, set[float]]]:
        """Every language's runs, by offset; runs that start at the same place pool their values."""
        at: dict[int, set[float]] = {}
        for lang in self.languages.values():
            for offset, vals in lang.spans(text):
                at.setdefault(offset, set()).update(vals)
        return sorted(at.items())
