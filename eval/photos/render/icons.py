"""Small vector icons drawn by consumer screens (watch faces, phone health apps): heart, drop, flame, moon, shoe,
thermometer, lungs. Each draws centered at (cx, cy) with overall size `s` and returns its box. Icons are decoration
next to a label; what a number measures is always also printed (or, for a heart, is the icon itself)."""
from __future__ import annotations

import math

from PIL import ImageDraw

Box = tuple[float, float, float, float]


def heart(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill) -> Box:
    """A heart: two lobes and a point, as on a heart-rate reading."""
    r = s * 0.27
    d.ellipse([cx - 2 * r, cy - s * 0.42, cx, cy - s * 0.42 + 2 * r], fill=fill)
    d.ellipse([cx, cy - s * 0.42, cx + 2 * r, cy - s * 0.42 + 2 * r], fill=fill)
    d.polygon([(cx - 1.93 * r, cy - s * 0.42 + 1.35 * r), (cx + 1.93 * r, cy - s * 0.42 + 1.35 * r),
               (cx, cy + s * 0.45)], fill=fill)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def drop(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill) -> Box:
    """A drop (blood oxygen)."""
    r = s * 0.3
    d.ellipse([cx - r, cy + s * 0.45 - 2 * r, cx + r, cy + s * 0.45], fill=fill)
    d.polygon([(cx, cy - s * 0.5), (cx - r * 0.97, cy + s * 0.45 - r * 1.25), (cx + r * 0.97, cy + s * 0.45 - r * 1.25)],
              fill=fill)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def flame(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill) -> Box:
    """A flame (calories)."""
    pts = []
    for k in range(40):
        t = 2 * math.pi * k / 40
        w = 0.32 * s * (1 - 0.55 * (1 - math.cos(t)) / 2) ** 0.5
        pts.append((cx + w * math.sin(t) * (1 + 0.2 * math.sin(3 * t)), cy + 0.1 * s - 0.4 * s * math.cos(t)))
    d.polygon(pts, fill=fill)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def moon(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill, bg) -> Box:
    """A crescent (sleep): a disc with a background-colored disc over one side."""
    r = s * 0.42
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    d.ellipse([cx - r * 0.35, cy - r * 1.05, cx + r * 1.45, cy + r * 0.75], fill=bg)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def shoe(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill) -> Box:
    """Two footprints (steps)."""
    for dx, dy in ((-0.18, 0.12), (0.18, -0.12)):
        x, y = cx + dx * s, cy + dy * s
        d.ellipse([x - 0.12 * s, y - 0.3 * s, x + 0.12 * s, y + 0.12 * s], fill=fill)
        d.ellipse([x - 0.09 * s, y + 0.16 * s, x + 0.09 * s, y + 0.32 * s], fill=fill)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def thermometer(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill) -> Box:
    """A thermometer (temperature)."""
    w = s * 0.16
    d.rounded_rectangle([cx - w, cy - s * 0.48, cx + w, cy + s * 0.2], int(w), outline=fill, width=max(2, int(s / 16)))
    d.ellipse([cx - 1.9 * w, cy + s * 0.1, cx + 1.9 * w, cy + s * 0.48], fill=fill)
    d.rectangle([cx - w * 0.45, cy - s * 0.2, cx + w * 0.45, cy + s * 0.2], fill=fill)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def lungs(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, fill) -> Box:
    """Two lobes and a windpipe (breathing rate)."""
    d.ellipse([cx - 0.46 * s, cy - 0.3 * s, cx - 0.06 * s, cy + 0.45 * s], fill=fill)
    d.ellipse([cx + 0.06 * s, cy - 0.3 * s, cx + 0.46 * s, cy + 0.45 * s], fill=fill)
    d.rectangle([cx - 0.04 * s, cy - 0.5 * s, cx + 0.04 * s, cy], fill=fill)
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


ICONS = {"heart": heart, "drop": drop, "flame": flame, "shoe": shoe, "thermometer": thermometer, "lungs": lungs}


def icon(d: ImageDraw.ImageDraw, name: str, cx: float, cy: float, s: float, fill, bg=None) -> Box:
    """Any icon by name (the moon needs the background color it is cut from)."""
    if name == "moon":
        return moon(d, cx, cy, s, fill, bg or (0, 0, 0))
    return ICONS[name](d, cx, cy, s, fill)
