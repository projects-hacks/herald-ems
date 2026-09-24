"""Split page texts into numbered, citable sections. Heading styles and noise rules come from config/knowledge.yaml."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


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


def strip_running_lines(pages: list[tuple[int, str]], share: float) -> list[tuple[int, list[str]]]:
    """Drop lines that repeat on most pages (running headers and footers) and page counters."""
    norm = lambda s: re.sub(r"\d+", "#", " ".join(s.split())).lower()
    counts = Counter(n for _, t in pages for n in {norm(line) for line in t.splitlines() if line.strip()})
    limit = max(2, int(round(share * len(pages))))
    out = []
    for p, t in pages:
        keep = [line for line in t.splitlines() if line.strip() and (len(pages) < 2 or counts[norm(line)] < limit)]
        out.append((p, keep))
    return out


class SectionSplitter:
    def __init__(self, heading_styles: dict, running_line_share: float, glyph_error_pattern: str):
        self.decimal = re.compile(heading_styles["decimal"])
        self.outline = [re.compile(p) for p in heading_styles["outline"]]
        self.share = running_line_share
        self.glyph_error = re.compile(glyph_error_pattern)

    def split(self, doc_id: str, pages: list[tuple[int, str]], style: str) -> list[Section]:
        lines = strip_running_lines(pages, self.share)
        sections: list[Section] = []
        stack: list[tuple[int, str, str]] = []           # (level, label, title)
        self._last_roman = 0
        for page, page_lines in lines:
            for line in page_lines:
                head = self._heading(line, style)
                if head:
                    level, label, title = head
                    stack = [s for s in stack if s[0] < level] + [(level, label, title)]
                    number = ".".join(s[1] for s in stack) if style == "outline" else label
                    sections.append(Section(doc_id, number, title.strip(), page, level, line.strip(),
                                            parents=[s[2] for s in stack[:-1]]))
                elif sections:
                    sections[-1].text += "\n" + line.strip()
                else:   # preamble (title, effective date) before the first numbered heading
                    sections.append(Section(doc_id, "0", line.strip(), page, 0, line.strip()))
        for s in sections:
            s.uncertain = bool(self.glyph_error.search(s.text))
        return sections

    def _heading(self, line: str, style: str):
        if style == "decimal":
            m = self.decimal.match(line)
            if m and not re.match(r"^\d+\s*(mg|mcg|ml|%|minutes?)\b", m.group(2), re.I):
                return m.group(1).count(".") + 1, m.group(1), m.group(2)
            return None
        for level, rx in enumerate(self.outline, start=1):
            m = rx.match(line)
            if not m:
                continue
            if level == 1:
                # "I."/"V."/"X." are also letters: a Roman heading must be the next numeral in sequence
                n = _roman(m.group(1))
                if n != self._last_roman + 1:
                    continue
                self._last_roman = n
            return level, m.group(1), m.group(2)
        return None


def _roman(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for i, ch in enumerate(s):
        v = vals[ch]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total
