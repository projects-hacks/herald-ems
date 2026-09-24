"""Printed things: prescription and over-the-counter labels, POLST-style forms, and distractor paper (receipt,
sticky note, visitor sign-in sheet). Same contract as displays.py: (spec, cfg, rng) -> (image, fields).
All names, numbers and addresses are fictitious."""
from __future__ import annotations

import random

from PIL import Image, ImageDraw

from .primitives import fit, text, union

INK = (25, 25, 30)


def _bottle(size, color) -> Image.Image:
    """An amber (or white) bottle seen from the side: body with a lighter vertical highlight and a cap."""
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 90, w - 1, h - 1], 40, fill=color)
    d.rectangle([40, 0, w - 41, 110], fill=(245, 245, 245))                    # cap
    for i in range(0, w - 80, 14):
        d.line([(40 + i, 0), (40 + i, 110)], fill=(215, 215, 215), width=3)
    hl = tuple(min(255, c + 45) for c in color[:3]) + (255,)
    d.rectangle([60, 120, 95, h - 30], fill=hl)
    return img


def pill_label(spec: dict, cfg: dict, rng: random.Random):
    img = _bottle((1260, 900), (170, 95, 30, 255))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 130, 180, 1180, 830
    d.rectangle([x0, y0, x1, y1], fill=(250, 250, 246), outline=(60, 60, 60), width=3)
    header = union(text(d, (x0 + 30, y0 + 25), "OAKRIDGE COMMUNITY PHARMACY", "sans_bold", 34, INK),
                   text(d, (x0 + 30, y0 + 68), "Rx# 0000-4417   (555) 010-2233", "sans", 28, INK))
    text(d, (x1 - 30, y0 + 25), "DATE 09/02/26", "sans", 26, INK, anchor="ra")
    text(d, (x0 + 30, y0 + 125), "SAMPLE, PATIENT", "sans_bold", 36, INK)
    drug = f"{spec['printed_name']} {spec['strength']} {spec.get('dose_form', 'TABLETS')}"
    size = fit(d, drug, "sans_bold", 56, x1 - x0 - 60)
    fields = {"drug": text(d, (x0 + 30, y0 + 190), drug, "sans_bold", size, INK)}
    y = fields["drug"][3] + 16
    if spec.get("printed_generic"):
        y = text(d, (x0 + 30, y), f"({spec['printed_generic']})", "sans_bold", 36, INK)[3] + 14
    text(d, (x0 + 30, y + 10), "TAKE AS DIRECTED BY YOUR PRESCRIBER", "sans", 32, INK)
    text(d, (x0 + 30, y + 70), "QTY: 30     REFILLS: 2     DR. A. EXAMPLE", "sans", 30, INK)
    if spec.get("generic_for"):
        text(d, (x0 + 30, y + 135), f"Generic for: {spec['generic_for']}", "sans_bold", 32, (110, 15, 15))
    text(d, (x1 - 30, y1 - 20), "Keep out of reach of children", "sans", 22, (90, 90, 90), anchor="rd")
    fields["header"] = header
    return img, fields


def otc_bottle(spec: dict, cfg: dict, rng: random.Random):
    img = _bottle((1100, 1000), (248, 248, 248, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([100, 200, 1000, 900], fill=(200, 30, 45))
    d.rectangle([100, 420, 1000, 700], fill=(255, 255, 255))
    text(d, (550, 250), "EVERYDAY VALUE", "sans_bold", 30, (255, 255, 255), anchor="ma")
    name = text(d, (550, 310), spec["printed_name"], "sans_bold", 72, (255, 255, 255), anchor="ma")
    strength = text(d, (550, 450), f"{spec['printed_generic'].title()} {spec['strength'].lower()}", "sans_bold", 64,
                    (200, 30, 45), anchor="ma")
    text(d, (550, 560), "Pain Reliever (NSAID)", "sans", 40, INK, anchor="ma")
    text(d, (550, 740), f"120 {spec['dose_form']}", "sans_bold", 36, (255, 255, 255), anchor="ma")
    return img, {"drug": union(name, strength)}


def _mark(d, box, kind: str, rng: random.Random):
    """A hand-drawn check or X in blue ink, with a little jitter."""
    x0, y0, x1, y1 = box
    j = lambda: rng.uniform(-3, 3)
    ink = (20, 40, 150)
    if kind == "x":
        d.line([(x0 + 4 + j(), y0 + 4 + j()), (x1 - 4 + j(), y1 - 4 + j())], fill=ink, width=7)
        d.line([(x1 - 4 + j(), y0 + 4 + j()), (x0 + 4 + j(), y1 - 4 + j())], fill=ink, width=7)
    else:
        d.line([(x0 + 2, (y0 + y1) / 2 + j()), (x0 + (x1 - x0) * 0.4, y1 - 2), (x1 + 12 + j(), y0 - 14 + j())],
               fill=ink, width=8, joint="curve")


def polst(spec: dict, cfg: dict, rng: random.Random):
    form = cfg["forms"]["polst"]
    W, H = 1100, 1250
    img = Image.new("RGB", (W, H), (252, 252, 248))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 110], fill=(215, 60, 110))
    text(d, (W / 2, 22), form["title"], "sans_bold", 34, (255, 255, 255), anchor="ma")
    text(d, (W / 2, 68), "(POLST) - SYNTHETIC SAMPLE FORM", "sans_bold", 26, (255, 255, 255), anchor="ma")
    text(d, (40, 135), "Patient Last Name: SAMPLE        First: PATIENT        DOB: 01/01/1940", "sans", 26, INK)
    fields, y = {}, 200
    for sec_key, chosen in (("section_a", spec.get("section_a")), ("section_b", spec.get("section_b"))):
        sec = form[sec_key]
        d.rectangle([30, y, W - 30, y + 60], fill=(235, 235, 235), outline=INK, width=2)
        text(d, (45, y + 16), sec["heading"], "sans_bold", fit(d, sec["heading"], "sans_bold", 24, W - 90), INK)
        y += 80
        for key, opt in sec["options"].items():
            label = opt["text"] if isinstance(opt, dict) else opt
            box = (60, y, 100, y + 40)
            d.rectangle(box, outline=INK, width=3)
            face = "sans_bold" if sec_key == "section_a" else "sans"
            fields[f"{sec_key}.{key}"] = text(d, (120, y + 4), label, face, fit(d, label, face, 30, W - 170), INK)
            if key == chosen:
                _mark(d, box, spec.get("mark", "check"), rng)
            y += 70
        y += 40
    d.rectangle([30, y, W - 30, y + 60], fill=(235, 235, 235), outline=INK, width=2)
    text(d, (45, y + 16), "C  SIGNATURE: PHYSICIAN / NP / PA", "sans_bold", 22, INK)
    for i, lab in enumerate(("Print name", "Signature", "Date")):
        yy = y + 120 + i * 80
        text(d, (60, yy - 34), lab, "sans", 24, (80, 80, 80))
        d.line([(60, yy), (W - 60, yy)], fill=INK, width=2)
    text(d, (W / 2, H - 40), "SEND FORM WITH PATIENT WHENEVER TRANSFERRED OR DISCHARGED", "sans_bold", 22,
         (215, 60, 110), anchor="ma")
    return img, fields


def receipt(spec: dict, cfg: dict, rng: random.Random):
    W, H = 640, 1100
    img = Image.new("RGB", (W, H), (250, 249, 244))
    d = ImageDraw.Draw(img)
    text(d, (W / 2, 40), "CORNER MARKET", "mono_bold", 40, INK, anchor="ma")
    text(d, (W / 2, 95), "123 EXAMPLE ST", "mono", 26, INK, anchor="ma")
    y, total = 190, 0.0
    for name, price in spec["lines"]:
        text(d, (40, y), name, "mono", 28, INK)
        text(d, (W - 40, y), price, "mono", 28, INK, anchor="ra")
        total += float(price)
        y += 50
    d.line([(40, y + 10), (W - 40, y + 10)], fill=INK, width=2)
    text(d, (40, y + 30), "TOTAL", "mono_bold", 32, INK)
    text(d, (W - 40, y + 30), f"{total:.2f}", "mono_bold", 32, INK, anchor="ra")
    text(d, (W / 2, y + 140), "THANK YOU", "mono", 28, INK, anchor="ma")
    return img, {}


def sticky_note(spec: dict, cfg: dict, rng: random.Random):
    img = Image.new("RGB", (800, 800), (253, 236, 120))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(spec["text"]):
        text(d, (60, 120 + i * 190), line, "serif_bold", 64, (30, 40, 120))
    return img, {}


def visitor_form(spec: dict, cfg: dict, rng: random.Random):
    W, H = 1100, 1300
    img = Image.new("RGB", (W, H), (252, 252, 250))
    d = ImageDraw.Draw(img)
    text(d, (W / 2, 40), "VISITOR SIGN-IN", "sans_bold", 50, INK, anchor="ma")
    cols = ["Name", "Time in", "Badge", "Escort?"]
    xs = [40, 480, 700, 900]
    for x, c in zip(xs, cols):
        text(d, (x, 140), c, "sans_bold", 30, INK)
    rows = [("A. Visitor", "09:10", "114", True), ("B. Guest", "10:45", "115", False), ("C. Caller", "13:20", "116", True)]
    for i, (n, t, b, esc) in enumerate(rows):
        y = 220 + i * 110
        d.line([(30, y + 80), (W - 30, y + 80)], fill=(150, 150, 150), width=2)
        for x, s in zip(xs[:3], (n, t, b)):
            text(d, (x, y + 20), s, "serif_bold", 36, (30, 40, 120))
        box = (xs[3] + 30, y + 15, xs[3] + 75, y + 60)
        d.rectangle(box, outline=INK, width=3)
        if esc:
            _mark(d, box, "check", rng)
    return img, {}


RENDERERS = {"pill_label": pill_label, "otc_bottle": otc_bottle, "polst": polst, "receipt": receipt,
             "sticky_note": sticky_note, "visitor_form": visitor_form}
