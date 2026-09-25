"""The real California POLST (EMSA #111 B, effective 4/1/2017; public form, capolst.org), filled in by hand.

The printed page is rendered once from the official PDF into content/ca_polst_2017.png, and the checkbox and
field positions (PDF points) are in content/ca_polst_2017.json (see docs/MODEL_PLAN.md §2a "POLST forms" for the
one-off prepare step). Every name, date and signature is invented. Handwriting comes from open-licensed (OFL)
Google Fonts in ~/.cache/herald-fonts/; the variant picks a font group, and group 3 is held out (dev and test).

What the answer is follows the production `form` prompt exactly: "full code" or "DNR" from the Section A box that
is clearly checked, nothing when no Section A box is clearly checked (only Section B marked, both A boxes marked, a
voided form, a blank form, a mark too faint to read). A blank Section A legally implies full treatment, but applying
that is the medic's call: the model reports only what is marked."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from random import Random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import canvas as cv
from .render_labels import TEXT, person
from .spec import Panel, Reading

CONTENT = Path(__file__).parent / "content"
FONT_DIR = Path.home() / ".cache" / "herald-fonts"
FONT_GROUPS = [["Caveat.ttf", "Kalam-Regular.ttf", "PatrickHand-Regular.ttf"],
               ["IndieFlower-Regular.ttf", "ShadowsIntoLight.ttf", "ArchitectsDaughter-Regular.ttf"],
               ["GochiHand-Regular.ttf", "NanumPenScript-Regular.ttf", "ReenieBeanie.ttf"],
               ["CoveredByYourGrace.ttf", "NothingYouCouldDo.ttf"]]          # group 3: dev / test only
SCENARIOS = [("cpr_full", 0.20), ("dnr_selective", 0.14), ("dnr_comfort", 0.12), ("dnr_full", 0.07),
             ("only_b", 0.10), ("both_a", 0.06), ("crossed", 0.10), ("void", 0.06), ("blank", 0.05),
             ("faint_readable", 0.06), ("faint_unreadable", 0.04)]
INKS = [(20, 40, 140), (15, 15, 20), (30, 30, 90), (60, 20, 20)]
RELATIONS = ["self", "self", "daughter", "son", "spouse", "wife", "husband", "conservator", "niece"]
ADDL = ["Trial of BiPAP OK", "No dialysis", "Comfort care at home if possible", "OK to transfer for hip fracture",
        "No blood transfusions", "Antibiotics OK", "Call daughter first"]


@lru_cache(maxsize=1)
def _page() -> tuple[Image.Image, dict]:
    meta = json.loads((CONTENT / "ca_polst_2017.json").read_text())
    return Image.open(CONTENT / "ca_polst_2017.png").convert("L"), meta


def fonts(variant: int) -> list[str]:
    paths = [str(FONT_DIR / f) for f in FONT_GROUPS[variant] if (FONT_DIR / f).exists()]
    if not paths:
        raise FileNotFoundError(f"handwriting fonts missing in {FONT_DIR} (docs/MODEL_PLAN.md §2a, POLST forms)")
    return paths


def _px(meta: dict, box) -> tuple[float, float, float, float]:
    s = meta["scale"]
    return tuple(v * s for v in box)


def _box(meta: dict, label: str):
    return next(_px(meta, b["box"]) for b in meta["boxes"] if b["label"].startswith(label))


def _mark(d: ImageDraw.ImageDraw, rng: Random, box, ink, style: str, width: int) -> None:
    """A hand-drawn mark in a checkbox: jittered strokes, never a perfect vector shape."""
    x0, y0, x1, y1 = box
    j = lambda v, a=2.5: v + rng.uniform(-a, a)
    if style == "check":
        d.line([(j(x0 + 2), j((y0 + y1) / 2)), (j((x0 + x1) / 2 - 1), j(y1)), (j(x1 + 10, 4), j(y0 - 14, 4))],
               fill=ink, width=width, joint="curve")
    elif style == "x":
        d.line([(j(x0), j(y0)), (j(x1 + 3), j(y1 + 2))], fill=ink, width=width)
        d.line([(j(x0), j(y1 + 2)), (j(x1 + 3), j(y0))], fill=ink, width=width)
    elif style == "fill":
        for k in range(int(y0) + 2, int(y1) - 1, 3):
            d.line([(j(x0 + 2, 1), k), (j(x1 - 2, 1), k + rng.uniform(-2, 2))], fill=ink, width=max(2, width - 1))
    elif style == "circle":                                   # circles the box and the start of its label
        cx, cy, rx, ry = x1 + 60, (y0 + y1) / 2, 95 + rng.uniform(-8, 20), 20 + rng.uniform(-3, 6)
        pts = [(cx + rx * math.cos(t) + rng.uniform(-1.5, 1.5), cy + ry * math.sin(t) + rng.uniform(-1.5, 1.5))
               for t in [i * 2 * math.pi / 40 + 0.3 for i in range(44)]]
        d.line(pts, fill=ink, width=width)
    else:                                                     # slash
        d.line([(j(x0), j(y1 + 3)), (j(x1 + 2), j(y0 - 3))], fill=ink, width=width)


def _write(d, rng: Random, xy, s: str, font: str, size: int, ink) -> cv.Box:
    return cv.text(d, (xy[0] + rng.uniform(-3, 3), xy[1] + rng.uniform(-2, 2)), s, font, size, ink)


def _signature(d, rng: Random, x: float, y: float, ink, width: int) -> None:
    pts, px = [], x
    for _ in range(rng.randint(14, 26)):
        px += rng.uniform(4, 14)
        pts.append((px, y + rng.uniform(-14, 10)))
    d.line(pts, fill=ink, width=width, joint="curve")


def _pick(rng: Random) -> str:
    r, acc = rng.random() * sum(w for _, w in SCENARIOS), 0.0
    for name, w in SCENARIOS:
        acc += w
        if r <= acc:
            return name
    return SCENARIOS[-1][0]


def ca_polst(rng: Random, variant: int, scenario: str | None = None) -> Panel:
    page, meta = _page()
    s = meta["scale"]
    scenario = scenario or _pick(rng)
    hands = fonts(variant)
    hand = rng.choice(hands)
    ink = cv.jitter(rng, rng.choice(INKS), 12)
    faint = scenario.startswith("faint")
    if faint:
        ink = (105, 105, 118) if scenario == "faint_readable" else (214, 210, 214)
    width = rng.choice([3, 4, 4, 5]) if not faint else 3
    img = page.convert("RGB")
    d = ImageDraw.Draw(img)
    fsz = int(rng.uniform(26, 34))
    texts, notes = [], [f"scenario={scenario}"]
    F = meta["fields"]

    # --- header: invented patient ---
    first, last = person(rng).split(" ", 1)
    for key, val in (("last", last), ("first", first), ("prepared", f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/{rng.choice([22, 23, 24, 25, 26])}"),
                     ("dob", f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/{rng.randint(1928, 1965)}")):
        if scenario == "blank" and rng.random() < 0.7:
            continue
        x0, y0, x1, y1 = _px(meta, F[key])
        _write(d, rng, (x0 + 6, y1 + 3), val, hand, fsz, ink)
        texts.append(val)

    # --- Section A ---
    cpr, dnr = _box(meta, "Attempt Resuscitation/CPR"), _box(meta, "Do Not Attempt Resuscitation/DNR")
    lab_w = 150 * s / 2.5
    style = rng.choice(["check", "check", "x", "fill", "circle", "slash"])
    readings = []
    a_choice = {"cpr_full": "cpr", "dnr_selective": "dnr", "dnr_comfort": "dnr", "dnr_full": "dnr",
                "faint_readable": rng.choice(["cpr", "dnr"]), "faint_unreadable": rng.choice(["cpr", "dnr"]),
                "crossed": rng.choice(["cpr", "dnr"])}.get(scenario)
    if scenario == "both_a":
        _mark(d, rng, cpr, ink, style, width)
        _mark(d, rng, dnr, ink, rng.choice(["check", "x"]), width)
        notes.append("both Section A boxes marked: ambiguous")
    if scenario == "crossed":                                  # the other box marked, then scribbled out
        wrong = dnr if a_choice == "cpr" else cpr
        _mark(d, rng, wrong, ink, "check", width)
        x0, y0, x1, y1 = wrong
        for k in range(4):                                     # a heavy scribble over the box and its label
            yk = y0 + (y1 - y0) * (k + 0.5) / 4
            d.line([(x0 - 8, yk + rng.uniform(-3, 3)), (x0 + lab_w * 1.1, yk + rng.uniform(-4, 4))], fill=ink, width=4)
        d.line([(x0 - 6, y1 + 4), (x0 + lab_w * 1.1, y0 - 4)], fill=ink, width=4)
        _write(d, rng, (x0 + lab_w + 190, y0 - 6), rng.choice(["JM", "RK", "void", "error"]), hand, fsz - 6, ink)
        notes.append("the first mark crossed out and initialed")
    if a_choice:
        box = cpr if a_choice == "cpr" else dnr
        _mark(d, rng, box, ink, style, width)
        readable = scenario != "faint_unreadable"
        value = "full code" if a_choice == "cpr" else "DNR"
        x0, y0, x1, y1 = box
        readings.append(Reading("code_status", value, (x0 - 4, y0 - 4, x1 + lab_w * 1.2, y1 + 4),
                                shown=value, readable=readable, why_unreadable="" if readable else "mark too faint"))

    # --- Section B (consistent with A: CPR requires Full Treatment) ---
    b_label = {"cpr_full": "Full Treatment", "dnr_full": "Full Treatment", "dnr_selective": "Selective Treatment",
               "dnr_comfort": "Comfort-Focused Treatment", "only_b": rng.choice(["Full Treatment", "Selective Treatment",
               "Comfort-Focused Treatment"])}.get(scenario, rng.choice(["Full Treatment", "Selective Treatment",
               "Comfort-Focused Treatment", None]))
    if b_label and scenario not in ("blank",):
        _mark(d, rng, _box(meta, b_label), ink, rng.choice(["check", "x", "fill"]), max(2, width - (1 if faint else 0)))
        if b_label == "Selective Treatment" and rng.random() < 0.4:
            _mark(d, rng, _box(meta, "Request transfer"), ink, "check", width)
    if rng.random() < 0.3 and scenario != "blank":
        x0, y0, x1, y1 = _px(meta, F["addl_b"])
        t = rng.choice(ADDL)
        _write(d, rng, (x1 + 10, y0 - 8), t, hand, fsz - 2, ink)
        texts.append(t)

    # --- Section C, D, signatures ---
    if scenario != "blank":
        _mark(d, rng, _box(meta, rng.choice(["Long-term", "Trial period of artificial", "No artificial"])), ink,
              rng.choice(["check", "x"]), width)
        _mark(d, rng, _box(meta, rng.choice(["Patient", "Legally Recognized"])), ink, "check", width)
        _mark(d, rng, _box(meta, rng.choice(["Advance Directive dated", "Advance Directive not", "No Advance"])), ink,
              "check", width)
        doc = f"Dr. {rng.choice(TEXT['last_names'])}"
        x0, y0, x1, y1 = _px(meta, F["phys_name"])
        texts.append(doc)
        _write(d, rng, (x0 + 4, y1 + 4), doc, hand, fsz, ink)
        x0, y0, x1, y1 = _px(meta, F["phys_phone"])
        _write(d, rng, (x0 + 4, y1 + 4), f"408-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}", hand, fsz - 4, ink)
        unsigned = rng.random() < 0.15
        if not unsigned:
            x0, y0, x1, y1 = _px(meta, F["phys_sig"])
            _signature(d, rng, x1 + 20, y1 + 12, ink, max(2, width - 1))
            x0, y0, x1, y1 = _px(meta, F["print_name"])
            pn = f"{first} {last}" if rng.random() < 0.5 else person(rng)
            _write(d, rng, (x1 + 10, y0 - 8), pn, hand, fsz, ink)
            texts.append(pn)
            x0, y0, x1, y1 = _px(meta, F["relationship"])
            _write(d, rng, (x1 + 10, y0 - 8), rng.choice(RELATIONS), hand, fsz - 2, ink)
            _signature(d, rng, 250, _px(meta, F["print_name"])[3] + 78, ink, max(2, width - 1))
        else:
            notes.append("unsigned (the mark is still read; validity is the medic's call)")
    if scenario == "void":
        top, bot = _px(meta, [0, 150, 0, 0])[1], _px(meta, [0, 0, 0, 700])[3]
        d.line([(120, bot), (img.width - 120, top)], fill=ink, width=6)
        cv.text(d, (img.width * 0.3, (top + bot) / 2 - 90), "VOID", hand, 190, ink)
        _signature(d, rng, img.width * 0.55, (top + bot) / 2 + 150, ink, 3)
        notes.append("voided form: no order")
        # a voided form may still show an A mark underneath; it is not an order
        if rng.random() < 0.6:
            _mark(d, rng, dnr if rng.random() < 0.5 else cpr, ink, "check", width)

    # --- framing: most phone photos aim at the orders (header through Section B or C), not the whole page.
    # Cropping only the bottom keeps every canvas coordinate valid. ---
    if rng.random() < 0.6:
        bottom = rng.choice([420, 500, 590]) * s                  # after B, after C, after D's first rows
        img = img.crop((0, 0, img.width, int(bottom)))
        notes.append(f"framed to y<{int(bottom / s)}pt")

    # --- paper: pink original or white photocopy; or the form shown on a screen ---
    on_screen = rng.random() < 0.25
    if not on_screen:
        tint = rng.choice([(255, 196, 214), (255, 205, 222), (250, 186, 206), (255, 255, 255), (244, 244, 240)])
        img = ImageChops.multiply(img, Image.new("RGB", img.size, tint))
        if rng.random() < 0.4:                                # fold lines
            fd = ImageDraw.Draw(img)
            for yf in (img.height / 3, 2 * img.height / 3):
                fd.line([(0, yf + rng.uniform(-8, 8)), (img.width, yf + rng.uniform(-8, 8))], fill=(150, 140, 145), width=2)
    else:
        img, pad = _on_screen(img, rng)
        readings = [Reading(r.key, r.value, tuple(v + pad for v in r.box), r.shown, r.readable,
                            why_unreadable=r.why_unreadable) for r in readings]
        notes.append("form displayed on a laptop/phone screen")
    panel = Panel(image=img.convert("RGBA"), readings=readings, family=f"ca_polst_2017/fonts{variant}/{'screen' if on_screen else 'paper'}",
                  device="polst_form", mode="form", texts=texts, notes=notes, flat=not on_screen,
                  distractors=["Section B/C/D marks", "additional orders", "signatures"])
    return panel


def _on_screen(img: Image.Image, rng: Random) -> tuple[Image.Image, int]:
    """The page as it looks on a laptop or phone display: dimmer, bluish, a moiré ripple, inside a dark bezel."""
    w, h = img.size
    scr = img.convert("RGB").point(lambda v: int(30 + v * 0.8))
    scr = ImageChops.multiply(scr, Image.new("RGB", scr.size, (235, 242, 255)))
    moire = Image.new("L", scr.size)
    md = ImageDraw.Draw(moire)
    period, angle = rng.uniform(5, 9), rng.uniform(-0.3, 0.3)
    for k in range(-h, w + h, int(period)):
        md.line([(k, 0), (k + angle * h, h)], fill=int(rng.uniform(14, 28)), width=2)
    moire = moire.filter(ImageFilter.GaussianBlur(1.2))
    scr = ImageChops.subtract(scr, Image.merge("RGB", (moire, moire, moire)))
    pad = int(w * rng.uniform(0.03, 0.06))
    out = Image.new("RGB", (w + 2 * pad, h + 2 * pad), cv.jitter(rng, (22, 22, 26), 8))
    out.paste(scr, (pad, pad))
    return out, pad
