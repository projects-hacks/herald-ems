"""Split page texts into numbered, citable sections. Heading styles and noise rules come from config/knowledge.yaml."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Section:
    doc_id: str
    number: str                 # "3.2.1", "VI.E.1.c"
    title: str                  # the heading line
    page: int
    level: int
    text: str = ""              # heading + body, as printed
    uncertain: bool = False     # the text layer shows font/ligature damage here
    parents: list[str] = field(default_factory=list)   # parent headings, for search context
    items: str = ""             # a lead-in section's sub-items, quoted with it but not indexed (they rank themselves)


def strip_running_lines(pages: list[tuple[int, str]], share: float, band: Optional[tuple[int, int]] = None,
                        keep: Callable[[str], bool] = lambda line: False) -> list[tuple[int, list[str]]]:
    """Drop running headers, footers, side tabs and page counters: a line (digits ignored, so "Page 2 of 3" matches
    "Page 3 of 3") that repeats on at least `share` of the pages. With a `band` (first, last), it must also sit among
    the first/last non-empty lines of its page in most of its occurrences, so body text that a short document prints
    twice (700-A14 §5.1 and §7.1, word for word on pages 1 and 2) stays. A line `keep` accepts (a numbered section is
    never a running line) always stays."""
    norm = lambda s: re.sub(r"\d+", "#", " ".join(s.split())).lower()
    counts = Counter(n for _, t in pages for n in {norm(line) for line in t.splitlines() if line.strip()})
    limit = max(2, int(round(share * len(pages))))
    in_band: dict[str, list[bool]] = defaultdict(list)
    for _, t in pages:
        body = [line for line in t.splitlines() if line.strip()]
        for i, line in enumerate(body):
            in_band[norm(line)].append(band is None or i < band[0] or len(body) - 1 - i < band[1])
    running = {n for n, c in counts.items() if c >= limit and 2 * sum(in_band[n]) > len(in_band[n])}
    out = []
    for p, t in pages:
        kept = [line for line in t.splitlines()
                if line.strip() and (len(pages) < 2 or norm(line) not in running or keep(line))]
        out.append((p, kept))
    return out


class SectionSplitter:
    def __init__(self, heading_styles: dict, running_line_share: float, glyph_error_pattern: str,
                 running_line_band: Optional[tuple[int, int]] = None, lead_in_children_chars: int = 0):
        self.decimal = re.compile(heading_styles["decimal"])
        self.outline = [re.compile(p) for p in heading_styles["outline"]]
        self.nested = re.compile(heading_styles["nested"]) if heading_styles.get("nested") else None
        self.share, self.band = running_line_share, tuple(running_line_band) if running_line_band else None
        self.glyph_error = re.compile(glyph_error_pattern)
        self.lead_in_chars = lead_in_children_chars

    def split(self, doc_id: str, pages: list[tuple[int, str]], style: str) -> list[Section]:
        lines = strip_running_lines(pages, self.share, self.band, lambda line: self._looks_like_heading(line, style))
        sections: list[Section] = []
        stack: list[tuple[int, str, str]] = []           # (level, label, title)
        self._last_roman = 0
        self._open: list[tuple[str, int]] = []           # nested style: (label kind, last value) of each open list
        for page, page_lines in lines:
            for line in page_lines:
                head = self._heading(line, style)
                if head:
                    level, label, title = head
                    stack = [s for s in stack if s[0] < level] + [(level, label, title)]
                    number = label if style == "decimal" else ".".join(s[1] for s in stack)
                    sections.append(Section(doc_id, number, title.strip(), page, level, line.strip(),
                                            parents=[s[2] for s in stack[:-1]]))
                elif sections:
                    sections[-1].text += "\n" + line.strip()
                else:   # preamble (title, effective date) before the first numbered heading
                    sections.append(Section(doc_id, "0", line.strip(), page, 0, line.strip()))
        if self.lead_in_chars:
            self._carry_lead_ins(sections)
        for s in sections:
            s.uncertain = bool(self.glyph_error.search(s.text))
        return sections

    def _carry_lead_ins(self, sections: list[Section]) -> None:
        """A section ending in a lead-in colon also carries its sub-items' text for quoting (the sub-items stay
        sections and are what search ranks, so a parent never outranks the item that says it)."""
        for i, s in enumerate(sections):
            if not s.text.rstrip().endswith(":") or s.level == 0:
                continue
            extra, used = [], 0
            for child in sections[i + 1:]:
                if child.level <= s.level or used + len(child.text) > self.lead_in_chars:
                    break
                extra.append(child.text); used += len(child.text)
            if extra:
                s.items = "\n".join(extra)

    def _looks_like_heading(self, line: str, style: str) -> bool:
        """The line has the shape of a numbered section in this style (no sequence check, no state change)."""
        patterns = {"decimal": [self.decimal], "nested": [self.nested]}.get(style, self.outline)
        return any(rx is not None and rx.match(line) for rx in patterns)

    def _heading(self, line: str, style: str):
        if style == "decimal":
            # The label's trailing period tells an item from a wrapped line that starts with a number; an item can
            # start with a dose ("3.2. 500 ml Normal Saline", 700-A10) or hold only a table ("3.3.1.3.", 700-P10).
            m = self.decimal.match(line)
            return (m.group(1).count(".") + 1, m.group(1), m.group(2) or "") if m else None
        if style == "nested":
            return self._nested_heading(line)
        for level, rx in enumerate(self.outline, start=1):
            m = rx.match(line)
            if not m:
                continue
            if level == 1:
                # "I."/"V."/"X." are also letters: a Roman heading must be the next numeral in sequence. A numeral
                # of two or more letters can't be a letter, so a printed repeat of it (Policy 605 prints "II." twice)
                # is a heading too.
                n = _roman(m.group(1))
                if n != self._last_roman + 1 and not (len(m.group(1)) > 1 and n == self._last_roman):
                    continue
                self._last_roman = n
            return level, m.group(1), m.group(2)
        return None

    def _nested_heading(self, line: str):
        """Deep outlines where a label kind recurs below itself ("I." > "A." > "1." > "a." > "i." > "1." > "a.",
        Policy 410), so the kind alone can't give the level. The next label of an open list continues that list (the
        deepest one first); the first label of a kind opens a list one level down; a Roman "I." always starts a new
        top-level section."""
        m = self.nested.match(line)
        if not m:
            return None
        label, title = m.group(1), m.group(2)
        kinds = [k for k, rx in _LABEL_KINDS if rx.fullmatch(label)]
        for depth in range(len(self._open) - 1, -1, -1):
            kind, value = self._open[depth]
            if kind in kinds and _ordinal(kind, label) == value + 1:
                self._open = self._open[:depth] + [(kind, value + 1)]
                return depth + 1, label, title
        for kind in kinds:
            if _ordinal(kind, label) == 1:
                depth = 0 if kind == "roman" else len(self._open)
                self._open = self._open[:depth] + [(kind, 1)]
                return depth + 1, label, title
        return None


_LABEL_KINDS = [("roman", re.compile(r"[IVXL]+")), ("upper", re.compile(r"[A-Z]")), ("number", re.compile(r"\d{1,2}")),
                ("lower", re.compile(r"[a-z]")), ("roman_lower", re.compile(r"[ivxl]+"))]


def _ordinal(kind: str, label: str) -> int:
    if kind in ("roman", "roman_lower"):
        return _roman(label.upper())
    if kind == "number":
        return int(label)
    return ord(label.lower()) - ord("a") + 1


def _roman(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for i, ch in enumerate(s):
        v = vals[ch]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total
