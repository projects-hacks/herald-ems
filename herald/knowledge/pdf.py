"""PDF text through poppler (`pdftotext -layout`), one string per page, with ligatures normalized (NFKC)."""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Optional

# Superscripts and subscripts keep their form. NFKC would turn them into plain characters and could silently change
# a number: 700-A18 sets "≥" in a Symbol font that the text layer reports as "³", and NFKC makes "SBP ³ 140" read
# "SBP 3 140". Kept, the glyph is visible and config/knowledge.yaml `glyph_error_pattern` flags the section.
_KEEP = re.compile("([\u00aa\u00b2\u00b3\u00b9\u00ba\u2070-\u209f])")   # ª ² ³ ¹ º and U+2070-U+209F


def normalize(text: str) -> str:
    """NFKC (ligatures such as "ﬃ" become "ffi") except superscript and subscript characters."""
    parts = _KEEP.split(text)
    return "".join(p if i % 2 else unicodedata.normalize("NFKC", p) for i, p in enumerate(parts))


def page_texts(path: Path, pages: Optional[tuple[int, int]] = None) -> list[tuple[int, str]]:
    """[(page number, text)], pages 1-based and inclusive."""
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    n = int(next(line.split()[-1] for line in info.splitlines() if line.startswith("Pages:")))
    first, last = pages or (1, n)
    out = []
    for p in range(first, last + 1):
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(path), "-"],
                             capture_output=True, text=True, check=True).stdout
        out.append((p, normalize(txt)))
    return out


def render_page(path: Path, page: int, out_png: Path, dpi: int = 110) -> Path:
    prefix = out_png.with_suffix("")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", "-singlefile",
                    str(path), str(prefix)], check=True, capture_output=True)
    return prefix.with_suffix(".png")
