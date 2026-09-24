"""Read check-mark grids (e.g. Policy 602 Table B) from a PDF's text layer.

Some county tables draw each check as a symbol-font character (in 602, the letter "R" in Wingdings2 renders as a
ticked box). Every word's position comes from `pdftotext -bbox-layout`; each check is assigned to the nearest
column header and row label. Which page and which glyph are per-document settings in the county config."""
from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


def _words(path: Path, page: int) -> list[tuple[float, float, float, float, str]]:
    out = subprocess.run(["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page), str(path), "-"],
                         capture_output=True, text=True, check=True).stdout
    return [(float(a), float(b), float(c), float(d), html.unescape(t)) for a, b, c, d, t in _WORD.findall(out)]


def read_check_table(path: Path, page: int, glyph: str, row_gap: float = 14.0, col_tol: float = 16.0) -> dict:
    words = _words(path, page)
    checks = [w for w in words if w[4] == glyph]
    if not checks:
        return {"columns": [], "rows": [], "cells": 0}
    top = min(w[1] for w in checks)
    left = min(w[0] for w in checks)
    # column headers: the line of short tokens nearest above the first check row, right of the label column
    header_ys = sorted({round(w[1]) for w in words if top - 40 < w[1] < top - 2 and w[0] >= left - col_tol})
    hy = header_ys[-1] if header_ys else None
    cols = sorted(((w[0] + w[2]) / 2, w[4]) for w in words if hy is not None and abs(w[1] - hy) < 2 and w[0] >= left - col_tol)
    # rows: anchored on the checks' own vertical positions (a label may wrap over two lines, and line spacing
    # inside a label is close to the spacing between rows, so gaps alone can't split them)
    centers: list[float] = []
    for cy in sorted((w[1] + w[3]) / 2 for w in checks):
        if not centers or cy - centers[-1] > 4:
            centers.append(cy)
    rows = [{"lines": [], "y": y, "checked": []} for y in centers]
    lines: dict[int, list] = {}
    for w in (w for w in words if w[2] < left - 2 and w[1] >= top - 12):
        lines.setdefault(round((w[1] + w[3]) / 2), []).append(w)
    for y, ws in sorted(lines.items()):
        text = " ".join(x[4] for x in sorted(ws))
        if text.startswith("*Note"):
            break
        near = min(rows, key=lambda r: abs(r["y"] - y))
        if abs(near["y"] - y) <= row_gap:
            near["lines"].append(text)
        else:                                   # a labelled row with no checks at all
            rows.append({"lines": [text], "y": y, "checked": []})
    rows.sort(key=lambda r: r["y"])
    for r in rows:
        r["label"] = " ".join(r.pop("lines")).lstrip("*").strip()
    for c in checks:
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        col = min(cols, key=lambda k: abs(k[0] - cx)) if cols else None
        row = min((r for r in rows if r["checked"] is not None), key=lambda r: abs(r["y"] - cy)) if rows else None
        if col and row and abs(col[0] - cx) <= col_tol:
            row["checked"].append(col[1])
    order = [c[1] for c in cols]
    for r in rows:
        r["checked"] = sorted(set(r["checked"]), key=order.index)
        r.pop("y")
    rows = [r for r in rows if r["label"]]
    return {"columns": order, "rows": rows, "cells": len(order) * len(rows)}


def read_column_table(path: Path, page: int, header: str, fields: list[str]) -> list[dict]:
    """A plain legend table (e.g. Policy 602 Table A: facility, city, ID): the lines after the line starting with
    `header`, up to the first blank line, split on runs of 2+ spaces."""
    text = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
                          capture_output=True, text=True, check=True).stdout.splitlines()
    start = next((i for i, line in enumerate(text) if line.strip().startswith(header)), None)
    if start is None:
        return []
    rows = []
    for line in text[start + 2:]:                 # skip the header line and the column-titles line
        if not line.strip():
            break
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) == len(fields):
            rows.append(dict(zip(fields, parts)))
    return rows
