"""PDF text through poppler (`pdftotext -layout`), one string per page, with ligatures normalized (NFKC)."""
from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path
from typing import Optional


def page_texts(path: Path, pages: Optional[tuple[int, int]] = None) -> list[tuple[int, str]]:
    """[(page number, text)], pages 1-based and inclusive."""
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    n = int(next(line.split()[-1] for line in info.splitlines() if line.startswith("Pages:")))
    first, last = pages or (1, n)
    out = []
    for p in range(first, last + 1):
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(path), "-"],
                             capture_output=True, text=True, check=True).stdout
        out.append((p, unicodedata.normalize("NFKC", txt)))
    return out


def render_page(path: Path, page: int, out_png: Path, dpi: int = 110) -> Path:
    prefix = out_png.with_suffix("")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", "-singlefile",
                    str(path), str(prefix)], check=True, capture_output=True)
    return prefix.with_suffix(".png")
