"""Drawing primitives shared by the renderers: fonts on this box, text that reports its box, seven-segment digits,
icons, waveforms and small charts. Pure PIL; no layouts here."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

from .spec import Box

_FONT_DIRS = ("/usr/share/fonts/truetype", "/usr/share/fonts/opentype")
FONT_FILES = {
    "sans": ["dejavu/DejaVuSans.ttf", "dejavu/DejaVuSans-Bold.ttf", "liberation/LiberationSans-Regular.ttf",
             "liberation/LiberationSans-Bold.ttf", "urw-base35/NimbusSans-Regular.otf", "urw-base35/NimbusSans-Bold.otf",
             "urw-base35/NimbusSansNarrow-Regular.otf", "urw-base35/NimbusSansNarrow-Bold.otf",
             "ubuntu/Ubuntu[wdth,wght].ttf", "ubuntu/UbuntuSans[wdth,wght].ttf", "cantarell/Cantarell-Regular.otf",
             "cantarell/Cantarell-Bold.otf", "urw-base35/URWGothic-Book.otf", "urw-base35/URWGothic-Demi.otf",
             "tlwg/Garuda.ttf", "tlwg/Loma.ttf", "tlwg/Umpush.ttf", "tlwg/Sawasdee.ttf"],
    "bold": ["dejavu/DejaVuSans-Bold.ttf", "liberation/LiberationSans-Bold.ttf", "urw-base35/NimbusSans-Bold.otf",
             "urw-base35/NimbusSansNarrow-Bold.otf", "cantarell/Cantarell-ExtraBold.otf", "urw-base35/URWGothic-Demi.otf",
             "tlwg/Garuda-Bold.ttf", "tlwg/Loma-Bold.ttf"],
    "mono": ["dejavu/DejaVuSansMono.ttf", "dejavu/DejaVuSansMono-Bold.ttf", "liberation/LiberationMono-Regular.ttf",
             "liberation/LiberationMono-Bold.ttf", "urw-base35/NimbusMonoPS-Regular.otf", "urw-base35/NimbusMonoPS-Bold.otf",
             "tlwg/TlwgTypewriter.ttf", "tlwg/TlwgMono.ttf", "noto/NotoSansMono-Regular.ttf", "noto/NotoSansMono-Bold.ttf"],
    "serif": ["dejavu/DejaVuSerif.ttf", "liberation/LiberationSerif-Regular.ttf", "liberation/LiberationSerif-Bold.ttf",
              "urw-base35/NimbusRoman-Regular.otf", "urw-base35/C059-Roman.otf", "urw-base35/P052-Roman.otf",
              "tlwg/Norasi.ttf", "tlwg/Kinnari.ttf", "fonts-yrsa-rasa/Yrsa-Regular.ttf"],
    "hand": ["tlwg/Purisa.ttf", "tlwg/Purisa-Bold.ttf", "malayalam/Chilanka-Regular.otf", "urw-base35/Z003-MediumItalic.otf",
             "tlwg/Purisa-Oblique.ttf", "tlwg/TlwgTypist-Oblique.ttf"],
}


def _resolve(rel: str) -> Optional[str]:
    for d in _FONT_DIRS:
        p = Path(d) / rel
        if p.exists():
            return str(p)
    return None


@lru_cache(maxsize=None)
def available(kind: str) -> tuple[str, ...]:
    found = tuple(p for p in (_resolve(r) for r in FONT_FILES[kind]) if p)
    if not found:
        raise RuntimeError(f"no {kind} fonts found under {_FONT_DIRS}")
    return found


@lru_cache(maxsize=4096)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(6, int(size)))


def pick_font(rng: Random, kind: str) -> str:
    return rng.choice(available(kind))


def text(draw: ImageDraw.ImageDraw, xy, s: str, path: str, size: int, fill, anchor: str = "la") -> Box:
    """Draw `s`; return its tight box."""
    f = font(path, size)
    draw.text(xy, s, font=f, fill=fill, anchor=anchor)
    return tuple(draw.textbbox(xy, s, font=f, anchor=anchor))


def text_size(s: str, path: str, size: int) -> tuple[int, int]:
    x0, y0, x1, y1 = font(path, size).getbbox(s)
    return x1 - x0, y1 - y0


def fit_size(s: str, path: str, max_w: float, max_h: float, start: int = 200) -> int:
    """Largest font size (<= start) whose rendering of `s` fits in max_w x max_h."""
    size = int(start)
    while size > 6:
        w, h = text_size(s, path, size)
        if w <= max_w and h <= max_h:
            return size
        size = int(size * 0.92)
    return 6


def union(*boxes: Optional[Box]) -> Optional[Box]:
    bs = [b for b in boxes if b]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


# ---------- seven-segment digits (LCD / LED displays) ----------
_SEGS = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg", "7": "abc",
         "8": "abcdefg", "9": "abcdfg", "-": "g", "H": "bcefg", "I": "bc", "L": "def", "O": "abcdef", "E": "adefg",
         "r": "eg", "o": "cdeg", "P": "abefg", "A": "abcefg", "C": "adef", "F": "aefg", "n": "ceg", "i": "c",
         "h": "cefg", "t": "defg", "u": "cde", "b": "cdefg", "d": "bcdeg", "S": "acdfg", " ": ""}


def seg_width(h: float) -> float:
    return h * 0.56


def seven_seg(draw: ImageDraw.ImageDraw, x: float, y: float, h: float, s: str, on, off=None,
              skew: float = 0.12, gap: float = 0.18) -> Box:
    """Draw `s` in seven-segment style with top-left (x, y) and digit height h; '.' is a dot after a digit."""
    w, t = seg_width(h), max(2.0, h * 0.14)
    cx, x_start = x, x
    for ch in s:
        if ch == ".":
            r = t * 0.85
            draw.ellipse([cx - w * gap * 0.9 - r, y + h - 2 * r, cx - w * gap * 0.9 + r, y + h], fill=on)
            continue
        segs = _SEGS.get(ch, "")

        def P(px, py):          # italic skew: shift right as we go up
            return (cx + px + (h - py) * skew, y + py)
        half = h / 2
        e = t * 0.35                     # small gap where segments meet
        lines = {"a": ((e, 0), (w - e, 0)), "d": ((e, h), (w - e, h)), "g": ((e, half), (w - e, half)),
                 "f": ((0, e), (0, half - e)), "b": ((w, e), (w, half - e)),
                 "e": ((0, half + e), (0, h - e)), "c": ((w, half + e), (w, h - e))}
        for name, ((x0, y0), (x1, y1)) in lines.items():
            col = on if name in segs else off
            if col is None:
                continue
            if y0 == y1:   # horizontal hexagon
                pts = [P(x0, y0), P(x0 + t / 2, y0 - t / 2), P(x1 - t / 2, y0 - t / 2), P(x1, y0),
                       P(x1 - t / 2, y0 + t / 2), P(x0 + t / 2, y0 + t / 2)]
            else:
                pts = [P(x0, y0), P(x0 + t / 2, y0 + t / 2), P(x0 + t / 2, y1 - t / 2), P(x0, y1),
                       P(x0 - t / 2, y1 - t / 2), P(x0 - t / 2, y0 + t / 2)]
            draw.polygon(pts, fill=col)
        cx += w * (1 + gap) + t
    return (x_start - t, y - t, cx + h * skew, y + h + t)


def seven_seg_width(s: str, h: float, gap: float = 0.18) -> float:
    w, t = seg_width(h), max(2.0, h * 0.14)
    return sum(0 if c == "." else w * (1 + gap) + t for c in s)


# ---------- icons and graphics ----------
def heart(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill) -> None:
    pts = []
    for i in range(40):
        t = 2 * math.pi * i / 40
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * r / 17, cy - y * r / 17))
    draw.polygon(pts, fill=fill)


def battery(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, level: float, color) -> None:
    draw.rectangle([x, y, x + w, y + h], outline=color, width=max(1, int(h / 8)))
    draw.rectangle([x + w, y + h * 0.3, x + w + h * 0.2, y + h * 0.7], fill=color)
    pad = max(1, h / 6)
    draw.rectangle([x + pad, y + pad, x + pad + (w - 2 * pad) * max(0.05, level), y + h - pad], fill=color)


def bars(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, n: int, lit: int, color, dim) -> None:
    bw = w / (n * 1.4)
    for i in range(n):
        bh = h * (i + 1) / n
        draw.rectangle([x + i * bw * 1.4, y + h - bh, x + i * bw * 1.4 + bw, y + h], fill=color if i < lit else dim)


def waveform(draw: ImageDraw.ImageDraw, rng: Random, box: Box, kind: str, color, width: int = 2) -> None:
    """ECG, pleth, resp or capnogram-like trace across the box."""
    x0, y0, x1, y1 = box
    h, n = y1 - y0, int(x1 - x0)
    period = rng.uniform(40, 110)
    pts = []
    for i in range(0, max(2, n), 2):
        ph = (i % period) / period
        if kind == "ecg":
            v = 0.1 * math.sin(ph * 2 * math.pi)
            if 0.30 < ph < 0.33:
                v = -0.2
            elif 0.33 <= ph < 0.37:
                v = 0.95 - (ph - 0.33) * 20
            elif 0.37 <= ph < 0.40:
                v = -0.3
            elif 0.55 < ph < 0.7:
                v = 0.25 * math.sin((ph - 0.55) / 0.15 * math.pi)
        elif kind == "pleth":
            v = math.sin(ph * math.pi) ** 3 * 0.8 + 0.15 * math.sin(ph * 4 * math.pi) * (ph > 0.5)
        elif kind == "co2":
            v = 0.85 if 0.3 < ph < 0.8 else 0.05
        else:
            v = 0.5 + 0.45 * math.sin(ph * 2 * math.pi)
        pts.append((x0 + i, y1 - h * 0.1 - (v + 0.3) / 1.4 * h * 0.8))
    draw.line(pts, fill=color, width=width)


def trend(draw: ImageDraw.ImageDraw, rng: Random, box: Box, color, n: int = 24, bars_style: bool = False,
          lo: float = 0.2, hi: float = 0.9, width: int = 2) -> None:
    x0, y0, x1, y1 = box
    vals, v = [], rng.uniform(lo, hi)
    for _ in range(n):
        v = min(hi, max(lo, v + rng.uniform(-0.12, 0.12)))
        vals.append(v)
    step = (x1 - x0) / n
    if bars_style:
        for i, v in enumerate(vals):
            draw.rectangle([x0 + i * step + step * 0.2, y1 - (y1 - y0) * v, x0 + (i + 1) * step - step * 0.2, y1],
                           fill=color)
    else:
        draw.line([(x0 + i * step, y1 - (y1 - y0) * v) for i, v in enumerate(vals)], fill=color, width=width)


def rounded(draw: ImageDraw.ImageDraw, box: Box, r: float, fill=None, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle([box[0], box[1], box[2], box[3]], radius=r, fill=fill, outline=outline, width=width)


def new_canvas(w: int, h: int, color=(0, 0, 0, 0)) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (int(w), int(h)), color)
    return im, ImageDraw.Draw(im)


def jitter(rng: Random, color: Iterable[int], amount: int = 18) -> tuple[int, ...]:
    return tuple(max(0, min(255, c + rng.randint(-amount, amount))) for c in color)
