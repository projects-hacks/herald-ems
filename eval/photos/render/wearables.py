"""Consumer wearables: smartwatch faces (round or rectangular) running a heart-rate, blood-oxygen or ECG app, and
a wrist blood-pressure monitor whose pulse is marked only by a heart icon. Same contract as displays.py: each
renderer returns (image, fields), fields mapping a vocabulary key to the box its value is drawn in."""
from __future__ import annotations

import random

from PIL import Image, ImageDraw

from .displays import LCD, _wave as wave
from .icons import drop, heart
from .primitives import rounded_panel, seven_segment, text

RED, WHITE, GREY, BLUE = (255, 55, 80), (245, 245, 245), (150, 152, 160), (90, 180, 255)


def _case(shape: str) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """The watch: straps above and below a case; returns the image and the screen box inside the case."""
    if shape == "round":
        W, H, cw = 700, 1150, 640
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([160, 0, 540, H], 60, fill=(45, 48, 55, 255))                  # strap
        top = (H - cw) // 2
        d.ellipse([30, top, 30 + cw, top + cw], fill=(150, 152, 158, 255))                 # case
        d.rounded_rectangle([660, top + 250, 700, top + 330], 12, fill=(120, 122, 128, 255))   # crown
        return img, (70, top + 40, 30 + cw - 40, top + cw - 40)
    W, H = 640, 1150
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([130, 0, 510, H], 60, fill=(210, 205, 196, 255))                   # strap
    top = (H - 700) // 2
    d.rounded_rectangle([40, top, 600, top + 700], 150, fill=(35, 36, 40, 255))            # case
    d.rounded_rectangle([600, top + 170, 632, top + 290], 14, fill=(70, 72, 78, 255))      # crown
    return img, (75, top + 35, 565, top + 665)


def smartwatch(spec: dict, cfg: dict, rng: random.Random):
    """spec: shape (round | rect), app (heart_rate | blood_oxygen | ecg), clock, and per app the extra lines."""
    v = spec["values"]
    img, (x0, y0, x1, y1) = _case(spec["shape"])
    scr = Image.new("RGB", (x1 - x0, y1 - y0), (0, 0, 0))
    mask = Image.new("L", scr.size, 0)
    md = ImageDraw.Draw(mask)
    if spec["shape"] == "round":
        md.ellipse([0, 0, scr.width - 1, scr.height - 1], fill=255)
    else:
        md.rounded_rectangle([0, 0, scr.width - 1, scr.height - 1], 120, fill=255)
    d = ImageDraw.Draw(scr)
    W, H = scr.size
    cx = W / 2
    f: dict = {}
    text(d, (cx, 40 if spec["shape"] == "round" else 30), spec.get("clock", "10:09"), "sans_bold", 40, WHITE,
         anchor="ma")
    app = spec["app"]
    if app == "heart_rate":
        if spec.get("label"):
            text(d, (cx, 100), spec["label"], "sans_bold", 38, RED, anchor="ma")
        heart(d, cx - 150, H * 0.47, 110, RED)
        f["vitals.hr"] = text(d, (cx - 80, H * 0.47), str(v["vitals.hr"]), "sans_bold", 170, WHITE, anchor="lm")
        text(d, (cx + 150, H * 0.62), "BPM", "sans_bold", 40, GREY, anchor="ma")
        if spec.get("resting") is not None:
            text(d, (cx, H * 0.76), f"Resting {spec['resting']} BPM", "sans", 36, GREY, anchor="ma")
        if spec.get("ago"):
            text(d, (cx, H * 0.84), spec["ago"], "sans", 30, GREY, anchor="ma")
    elif app == "blood_oxygen":
        text(d, (cx, 100), spec.get("label", "Blood Oxygen"), "sans_bold", 40, BLUE, anchor="ma")
        drop(d, cx, H * 0.33, 80, BLUE)
        f["vitals.spo2"] = text(d, (cx, H * 0.56), f"{v['vitals.spo2']}%", "sans_bold", 160, WHITE, anchor="mm")
        text(d, (cx, H * 0.75), spec.get("when", "Measured just now"), "sans", 32, GREY, anchor="ma")
    elif app == "ecg":
        text(d, (cx, 100), "ECG", "sans_bold", 42, RED, anchor="ma")
        wave(d, (40, H * 0.24, W - 40, H * 0.44), "ecg", v["vitals.hr"], RED, width=4)
        text(d, (cx, H * 0.50), spec.get("result", "Sinus Rhythm"), "sans_bold", 50, WHITE, anchor="ma")
        f["vitals.hr"] = text(d, (cx - 20, H * 0.63), str(v["vitals.hr"]), "sans_bold", 100, WHITE, anchor="ra")
        text(d, (cx, H * 0.66), "BPM", "sans_bold", 40, GREY, anchor="la")
        text(d, (cx, H * 0.72), "Average", "sans", 34, GREY, anchor="la")
        text(d, (cx, H * 0.85), spec.get("footer", "30 s recording complete"), "sans", 28, GREY, anchor="ma")
    else:
        raise ValueError(f"unknown watch app {app!r}")
    img.paste(scr, (x0, y0), mask)
    return img, {k: (b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0) for k, b in f.items()}


def wrist_bp_cuff(spec: dict, cfg: dict, rng: random.Random):
    """A wrist cuff: SYS and DIA in seven segments, the pulse next to a heart icon (no PULSE word), the date and
    time, and a memory-slot number (a number that is not a vital)."""
    v = spec["values"]
    W, H = 1100, 640
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 190, W, 450], fill=(60, 64, 72, 255))                                   # the cuff band
    body = rounded_panel((860, 620), 80, (236, 238, 240, 255), outline=(170, 172, 176), width=4)
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle([60, 50, 800, 500], 18, fill=LCD["bg"], outline=(110, 110, 110), width=3)
    on, off = LCD["on"], LCD["off"]
    seven_segment(bd, 90, 70, spec.get("date", "9-24"), 40, on, off)
    seven_segment(bd, 300, 70, spec.get("time", "7:42"), 40, on, off)
    f = {}
    for key, lab, y in (("vitals.sbp", "SYS", 135), ("vitals.dbp", "DIA", 300)):
        text(bd, (90, y + 10), lab, "sans_bold", 30, on)
        text(bd, (90, y + 50), "mmHg", "sans", 22, on)
        f[key] = seven_segment(bd, 230, y, str(v[key]).rjust(3), 140, on, off)
    heart(bd, 690, 190, 60, on)
    f["vitals.hr"] = seven_segment(bd, 610, 250, str(v["vitals.hr"]).rjust(3), 80, on, off, gap=0.2)
    text(bd, (770, 345), "/min", "sans_bold", 26, on, anchor="ra")
    text(bd, (620, 70), "M", "sans_bold", 34, on)
    seven_segment(bd, 665, 72, str(spec.get("memory", 12)), 36, on, off)
    bd.ellipse([370, 525, 490, 600], fill=(40, 90, 170))
    text(bd, (430, 562), "START", "sans_bold", 22, (255, 255, 255), anchor="mm")
    img.paste(body, (120, 10), body)
    return img, {k: (b[0] + 120, b[1] + 10, b[2] + 120, b[3] + 10) for k, b in f.items()}


RENDERERS = {"smartwatch": smartwatch, "wrist_bp_cuff": wrist_bp_cuff}
