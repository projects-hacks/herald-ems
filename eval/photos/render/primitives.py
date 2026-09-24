"""Drawing primitives for the synthetic photo set: fonts, seven-segment digits, and placing a rendered device on a
photo-like background (surface texture, shadow). Pure Pillow + numpy; deterministic given the caller's rng."""
from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIRS = (Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/liberation"))
FONTS = {
    "sans": "DejaVuSans.ttf", "sans_bold": "DejaVuSans-Bold.ttf", "mono": "DejaVuSansMono.ttf",
    "mono_bold": "DejaVuSansMono-Bold.ttf", "narrow": "LiberationSansNarrow-Regular.ttf",
    "narrow_bold": "LiberationSansNarrow-Bold.ttf", "serif_bold": "DejaVuSerif-Bold.ttf",
    "arial": "LiberationSans-Regular.ttf", "arial_bold": "LiberationSans-Bold.ttf",
}

Box = tuple[float, float, float, float]


@lru_cache(maxsize=None)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        p = d / FONTS.get(name, name)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype(str(FONT_DIRS[0] / FONTS["sans"]), size)


def text(draw: ImageDraw.ImageDraw, xy, s: str, name: str, size: int, fill, anchor: str = "la") -> Box:
    """Draw text and return its bounding box."""
    f = font(name, size)
    draw.text(xy, s, font=f, fill=fill, anchor=anchor)
    return draw.textbbox(xy, s, font=f, anchor=anchor)


def fit(draw: ImageDraw.ImageDraw, s: str, name: str, size: int, width: float) -> int:
    """The largest font size <= `size` at which `s` fits in `width` pixels."""
    while size > 12 and draw.textlength(s, font=font(name, size)) > width:
        size -= 2
    return size


def union(*boxes: Box) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


# ---------- seven-segment LCD digits ----------
#   segments: a top, b upper right, c lower right, d bottom, e lower left, f upper left, g middle
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
    "8": "abcdefg", "9": "abcdfg", "-": "g", "H": "fbgec", "I": "bc", "L": "fed", "o": "gcde", " ": "",
}


def _segment_polys(x: float, y: float, w: float, h: float, t: float) -> dict[str, list[tuple[float, float]]]:
    """Hexagonal segments for one digit cell at (x, y) of size w x h, stroke t, with a slight italic slant."""
    s = 0.12 * w                                   # slant: top shifted right
    def P(px, py):                                 # slanted point
        return (x + px + s * (1 - py / h), y + py)
    m, g = t / 2, h / 2
    horiz = lambda py: [P(m, py), P(m + t / 2, py - m), P(w - m - t / 2, py - m), P(w - m, py),
                        P(w - m - t / 2, py + m), P(m + t / 2, py + m)]
    vert = lambda px, y0, y1: [P(px, y0 + m), P(px + m, y0 + m + t / 2), P(px + m, y1 - m - t / 2), P(px, y1 - m),
                               P(px - m, y1 - m - t / 2), P(px - m, y0 + m + t / 2)]
    return {"a": horiz(m), "g": horiz(g), "d": horiz(h - m),
            "f": vert(m, 0, g), "b": vert(w - m, 0, g), "e": vert(m, g, h), "c": vert(w - m, g, h)}


def seven_segment(draw: ImageDraw.ImageDraw, x: float, y: float, s: str, h: float, on, off=None,
                  gap: float = 0.25) -> Box:
    """Draw `s` in seven-segment digits (':' and '.' supported) with its top-left at (x, y); returns the box."""
    w, t = 0.55 * h, 0.12 * h
    cx = x
    for ch in s:
        if ch in ".:":
            r = t * 0.55
            dots = [y + h - r] if ch == "." else [y + h * 0.3, y + h * 0.7]
            for dy in dots:
                draw.ellipse([cx + r * 0.5, dy - r, cx + r * 2.5, dy + r], fill=on)
            cx += r * 3.5
            continue
        polys = _segment_polys(cx, y, w, h, t)
        for name, poly in polys.items():
            lit = name in SEGMENTS.get(ch, "")
            if lit or off is not None:
                draw.polygon(poly, fill=on if lit else off)
        cx += w * (1 + gap)
    return (x, y, cx, y + h)


# ---------- photo composition ----------
def surface(size: tuple[int, int], rng: random.Random) -> Image.Image:
    """A table/bedsheet-like background: a soft gradient in a muted color with fine noise."""
    w, h = size
    base = np.array(rng.choice([(150, 132, 110), (190, 190, 185), (95, 100, 110), (170, 150, 125), (120, 130, 125)]),
                    dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(0, np.pi)
    grad = ((np.cos(ang) * xx / w + np.sin(ang) * yy / h) - 0.5) * rng.uniform(30, 60)
    nrng = np.random.default_rng(rng.randrange(2 ** 31))
    noise = nrng.normal(0, 6, (h, w)).astype(np.float32)
    img = base[None, None, :] + (grad + noise)[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(0.6))


def place(device: Image.Image, fields: dict[str, Box], canvas: tuple[int, int], rng: random.Random,
          fill: float = 0.78) -> tuple[Image.Image, dict[str, Box]]:
    """Put the device on a background, scaled to about `fill` of the frame, off-center, with a drop shadow.
    Returns the photo and the device's field boxes in photo coordinates."""
    cw, ch = canvas
    scale = min(cw * fill / device.width, ch * fill / device.height)
    dev = device.resize((int(device.width * scale), int(device.height * scale)), Image.LANCZOS)
    bg = surface(canvas, rng)
    x = int((cw - dev.width) / 2 + rng.uniform(-0.25, 0.25) * (cw - dev.width))
    y = int((ch - dev.height) / 2 + rng.uniform(-0.25, 0.25) * (ch - dev.height))
    shadow = Image.new("L", canvas, 0)
    ImageDraw.Draw(shadow).rounded_rectangle([x + 10, y + 14, x + dev.width + 10, y + dev.height + 14], 18, fill=120)
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    bg = Image.composite(Image.new("RGB", canvas, (20, 20, 20)), bg, shadow)
    mask = device.split()[3].resize(dev.size) if device.mode == "RGBA" else None
    bg.paste(dev.convert("RGB"), (x, y), mask)
    moved = {k: (x + b[0] * scale, y + b[1] * scale, x + b[2] * scale, y + b[3] * scale) for k, b in fields.items()}
    return bg, moved


def rounded_panel(size: tuple[int, int], radius: int, fill, outline=None, width: int = 0) -> Image.Image:
    """An RGBA image holding one rounded rectangle (device bodies are drawn on these)."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, fill=fill, outline=outline,
                                          width=width)
    return img
