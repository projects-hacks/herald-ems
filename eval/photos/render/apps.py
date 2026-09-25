"""Phone health and fitness app screens, and a tablet showing a picture of a bedside monitor. Same contract as
displays.py.

A phone screen is data (eval/photos/specs.yaml): a title, an optional hero reading, an optional chart, and a list of
cards. A card or the hero shows a vocabulary key's value from the item's `values` (`key`, or `keys` for a pair such
as SBP/DBP) or a literal `value` (a distractor: steps, a resting or average rate, a range, a history entry). Every
key in `values` must be drawn somewhere, so the gold always matches what the image shows."""
from __future__ import annotations

import random

from PIL import Image, ImageDraw

from .displays import bedside_monitor
from .icons import icon
from .primitives import fit, rounded_panel, text

THEMES = {
    "light": {"bg": (242, 242, 247), "card": (255, 255, 255), "text": (20, 20, 24), "sub": (120, 120, 128),
              "line": (220, 220, 226)},
    "dark": {"bg": (14, 16, 20), "card": (32, 35, 42), "text": (240, 240, 244), "sub": (150, 154, 164),
             "line": (60, 64, 74)},
}
COLORS = {"red": (235, 60, 80), "blue": (40, 140, 240), "green": (40, 180, 100), "orange": (245, 140, 30),
          "purple": (150, 90, 230), "teal": (30, 170, 180), "grey": (140, 140, 150)}


def shown(spec: dict, part: dict) -> tuple[str, list[str]]:
    """The text a card or hero displays, and the vocabulary keys it carries."""
    if "keys" in part:
        return "/".join(str(spec["values"][k]) for k in part["keys"]), list(part["keys"])
    if "key" in part:
        v = spec["values"][part["key"]]
        if part["key"] == "vitals.temp" and spec.get("temp_unit") == "F":
            v = f"{v * 9 / 5 + 32:.1f}"
        return str(v), [part["key"]]
    return str(part["value"]), []


def _status_bar(d, W: int, th: dict, spec: dict) -> None:
    text(d, (48, 26), spec.get("clock", "9:41"), "sans_bold", 30, th["text"])
    batt = spec.get("battery", 87)
    text(d, (W - 110, 26), f"{batt}%", "sans_bold", 26, th["text"], anchor="ra")
    d.rounded_rectangle([W - 96, 28, W - 48, 54], 6, outline=th["text"], width=3)
    d.rectangle([W - 92, 32, W - 92 + int(40 * batt / 100), 50], fill=th["text"])


def _hero(d, spec: dict, th: dict, W: int, y: int, f: dict) -> int:
    h = spec["hero"]
    col = COLORS[h.get("color", "red")]
    if h.get("label"):
        icon(d, h.get("icon", "heart"), 66, y + 22, 36, col, th["bg"])
        text(d, (96, y + 6), h["label"], "sans_bold", 32, col)
        y += 56
    s, keys = shown(spec, h)
    b = text(d, (48, y), s, "sans_bold", 150, th["text"])
    for k in keys:
        f[k] = b
    end = b[2]
    if h.get("unit"):
        end = text(d, (b[2] + 16, b[3] - 16), h["unit"], "sans_bold", 42, th["sub"], anchor="ld")[2]
    if h.get("arrow"):                                            # a trend arrow after the unit
        text(d, (end + 24, b[1] + (b[3] - b[1]) / 2), h["arrow"], "sans_bold", 90, col, anchor="lm")
    y = b[3] + 18
    for line in h.get("notes", []):
        text(d, (48, y), line, "sans", 28, th["sub"])
        y += 40
    return y + 16


def _chart(d, spec: dict, th: dict, W: int, y: int, rng: random.Random) -> int:
    c = spec["chart"]
    col = COLORS[c.get("color", "red")]
    if c.get("header"):
        text(d, (48, y), c["header"], "sans_bold", 24, th["sub"])
        b = text(d, (48, y + 32), c["big"], "sans_bold", 72, th["text"])
        text(d, (b[2] + 12, b[3] - 8), c.get("unit", ""), "sans_bold", 32, th["sub"], anchor="ld")
        text(d, (48, b[3] + 10), c.get("sub", ""), "sans", 26, th["sub"])
        y = b[3] + 56
    x0, x1, top, bot = 48, W - 110, y + 10, y + 300
    d.rectangle([x0 - 10, top - 10, W - 40, bot + 40], fill=th["card"])
    lo, hi = c["axis"]
    ypos = lambda val: bot - (val - lo) / (hi - lo) * (bot - top)
    for g in c.get("gridlines", []):
        d.line([(x0, ypos(g)), (x1, ypos(g))], fill=th["line"], width=2)
        text(d, (x1 + 10, ypos(g)), str(g), "sans", 24, th["sub"], anchor="lm")
    if c["kind"] == "range_bars":
        days = c.get("days", ["TH", "F", "SA", "SU", "M", "TU", "W"])
        step = (x1 - x0) / len(days)
        for i, day in enumerate(days):
            a = rng.uniform(c["low"], c["low"] + 15)
            b_ = rng.uniform(c["high"] - 30, c["high"])
            if i == c.get("peak_day", 3):
                a, b_ = c["low"], c["high"]
            cx = x0 + (i + 0.5) * step
            d.rounded_rectangle([cx - 12, ypos(b_), cx + 12, ypos(a)], 12, fill=col)
            text(d, (cx, bot + 10), day, "sans", 22, th["sub"], anchor="ma")
    else:                                                          # line: readings every 5 minutes
        n, pts = 36, []
        level = c.get("start", (lo + hi) / 2)
        for i in range(n):
            level += (c["end"] - level) / (n - i) + rng.uniform(-4, 4)
            pts.append((x0 + i * (x1 - x0) / (n - 1), ypos(level)))
        for p in pts:
            d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], fill=col)
        for k, lab in enumerate(c.get("x_labels", [])):
            text(d, (x0 + k * (x1 - x0) / max(1, len(c["x_labels"]) - 1), bot + 10), lab, "sans", 22, th["sub"],
                 anchor="ma")
    return bot + 70


def _card(d, spec: dict, card: dict, th: dict, W: int, y: int, f: dict) -> int:
    h = 146 if card.get("note") or card.get("title") else 110
    d.rounded_rectangle([32, y, W - 32, y + h], 24, fill=th["card"])
    col = COLORS[card.get("color", "grey")]
    ty = y + 22
    if card.get("title"):
        if card.get("icon"):
            icon(d, card["icon"], 70, ty + 16, 32, col, th["card"])
        text(d, (100 if card.get("icon") else 56, ty), card["title"], "sans_bold", 28, col)
        if card.get("note"):
            text(d, (W - 56, ty + 2), card["note"], "sans", 24, th["sub"], anchor="ra")
        ty += 48
    s, keys = shown(spec, card)
    size = fit(d, s, "sans_bold", 66, W - 300)
    b = text(d, (56, ty), s, "sans_bold", size, th["text"])
    for k in keys:
        f[k] = b
    if card.get("unit"):
        text(d, (b[2] + 12, b[3] - 4), card["unit"], "sans_bold", 30, th["sub"], anchor="ld")
    return y + h + 16


def phone_app(spec: dict, cfg: dict, rng: random.Random):
    th = THEMES[spec.get("style", "light")]
    W, H = 640, 1390
    body = rounded_panel((W + 48, H + 48), 90, (18, 18, 20, 255))
    scr = Image.new("RGB", (W, H), th["bg"])
    d = ImageDraw.Draw(scr)
    _status_bar(d, W, th, spec)
    f: dict = {}
    y = 80
    if spec.get("back"):
        text(d, (40, y), "< " + spec["back"], "sans", 30, COLORS["blue"])
        y += 50
    text(d, (48, y), spec["title"], "sans_bold", 54, th["text"])
    y += 80
    if spec.get("subtitle"):
        text(d, (48, y - 10), spec["subtitle"], "sans", 28, th["sub"])
        y += 40
    if spec.get("hero"):
        y = _hero(d, spec, th, W, y, f)
    if spec.get("chart"):
        y = _chart(d, spec, th, W, y, rng)
    if spec.get("section"):
        text(d, (48, y), spec["section"], "sans_bold", 30, th["sub"])
        y += 48
    for card in spec.get("cards", []):
        y = _card(d, spec, card, th, W, y, f)
    if y > H:
        raise ValueError(f"{spec['id']}: the screen content does not fit ({y} > {H} px)")
    missing = set(spec.get("values", {})) - set(f)
    if missing:
        raise ValueError(f"{spec['id']}: values not drawn on the screen: {sorted(missing)}")
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], 70, fill=255)
    body.paste(scr, (24, 24), mask)
    return body, {k: (b[0] + 24, b[1] + 24, b[2] + 24, b[3] + 24) for k, b in f.items()}


def tablet_monitor(spec: dict, cfg: dict, rng: random.Random):
    """A tablet held up showing a picture of a bedside monitor (e.g. a photo sent by a colleague): the bedside
    monitor renderer's image inside a tablet bezel, with a caption bar of the viewer app."""
    mon, fields = bedside_monitor(spec, cfg, rng)
    W, H = 1500, 1080
    body = rounded_panel((W, H), 60, (28, 28, 30, 255))
    bd = ImageDraw.Draw(body)
    scr = (60, 60, W - 60, H - 60)
    bd.rectangle(scr, fill=(0, 0, 0))
    text(bd, (90, 80), spec.get("caption", "IMG_2291.JPG"), "sans", 26, (200, 200, 200))
    s = min((scr[2] - scr[0] - 40) / mon.width, (scr[3] - scr[1] - 110) / mon.height)
    m = mon.resize((int(mon.width * s), int(mon.height * s)), Image.LANCZOS)
    ox, oy = scr[0] + (scr[2] - scr[0] - m.width) // 2, scr[1] + 70
    body.paste(m, (ox, oy), m)
    return body, {k: (ox + b[0] * s, oy + b[1] * s, ox + b[2] * s, oy + b[3] * s) for k, b in fields.items()}


RENDERERS = {"phone_app": phone_app, "tablet_monitor": tablet_monitor}
