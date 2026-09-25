"""Medication labels: pharmacy bottle labels, stock bottles and cartons, blister foil, inhalers, insulin pens,
patch boxes, and printed or handwritten medication lists. Every product is a real RxNorm product (drugs.py);
people, pharmacies and prescribers are synthetic (content/text.yaml)."""
from __future__ import annotations

from pathlib import Path
from random import Random

import numpy as np
import yaml
from PIL import Image

from . import canvas as cv
from .drugs import Catalog, Product
from .spec import Panel, Reading

TEXT = yaml.safe_load((Path(__file__).resolve().parent / "content" / "text.yaml").read_text())
FORM_ABBR = {"oral tablet": ["TAB", "TABLET", "Tablet", "tab"], "oral capsule": ["CAP", "CAPSULE", "Capsule", "cap"],
             "extended release oral tablet": ["ER TAB", "TAB ER", "XL Tablet", "ER Tablet"],
             "extended release oral capsule": ["ER CAP", "CAP ER", "XR Capsule"],
             "delayed release oral tablet": ["DR TAB", "EC TAB", "DR Tablet"],
             "delayed release oral capsule": ["DR CAP", "DR Capsule"]}
SALT_ABBR = {"hydrochloride": "HCL", "tartrate": "TART", "succinate": "SUCC", "sodium": "SOD", "potassium": "POT",
             "besylate": "BESY", "calcium": "CALC", "maleate": "MAL", "mesylate": "MES", "citrate": "CIT"}


def person(rng: Random) -> str:
    return f"{rng.choice(TEXT['first_names'])} {rng.choice(TEXT['last_names'])}"


def strength_text(rng: Random, p: Product) -> str:
    unit = p.unit if rng.random() < 0.5 else p.unit.upper().replace("UNITS/ML", "UNITS/mL")
    return rng.choice([f"{p.number} {unit}", f"{p.number}{unit}", f"{p.number} {unit}"])


def drug_text(rng: Random, p: Product, allow_brand: bool = True) -> tuple[str, bool]:
    """How a label names the product (generic with salt, abbreviated salt, or the brand); True if brand."""
    if allow_brand and p.brands and rng.random() < 0.35:
        return rng.choice(p.brands).upper() if rng.random() < 0.6 else rng.choice(p.brands).title(), True
    g = p.generic
    if rng.random() < 0.3:
        g = " ".join(SALT_ABBR.get(w, w) for w in g.split())
    return (g.upper() if rng.random() < 0.6 else g.title()), False


def _form_word(rng: Random, p: Product) -> str:
    return rng.choice(FORM_ABBR.get(p.form, [p.form.split()[-1].upper()]))


def cylinder(im: Image.Image, radius_frac: float, readings: list[Reading]) -> Image.Image:
    """Wrap a flat label around a bottle: columns compress toward the edges; boxes follow; edges darken."""
    w, h = im.size
    cx, r = w / 2, w * radius_frac
    xo = np.arange(w)
    rel = np.clip((xo - cx) / r, -0.999, 0.999)
    src = np.clip(cx + r * np.arcsin(rel), 0, w - 1).astype(int)
    arr = np.asarray(im)[:, src]
    shade = (0.55 + 0.45 * np.cos(np.arcsin(rel)))[None, :, None]
    arr = arr.astype(np.float32)
    arr[..., :3] *= shade
    out = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
    fx = lambda x: cx + r * np.sin(np.clip((x - cx) / r, -np.pi / 2, np.pi / 2))
    for rd in readings:
        for attr in ("box", "strength_box"):
            b = getattr(rd, attr)
            if b:
                setattr(rd, attr, (float(fx(b[0])), b[1], float(fx(b[2])), b[3]))
    return out


def _med(p: Product, name_box, strength_box, shown: str) -> Reading:
    return Reading("meds.list", p.ingredient, cv.union(name_box, strength_box), shown, strength=p.strength,
                   strength_box=strength_box)


def pharmacy_label(rng: Random, variant: int, catalog: Catalog) -> Panel:
    """Variants: 0 header band, 1 barcode column, 2 patient-first modern, 3 (held out) field-labelled table."""
    p = catalog.pick(rng, "bottle")
    W, H = 900, 560
    paper = rng.choice([(255, 255, 255), (250, 250, 240), (255, 253, 245)])
    im, d = cv.new_canvas(W, H, paper + (255,))
    ink = rng.choice([(10, 10, 10), (20, 20, 60), (40, 40, 40)])
    f_reg, f_bold = cv.pick_font(rng, rng.choice(["sans", "mono"])), cv.pick_font(rng, "bold")
    pharm = rng.choice(TEXT["pharmacies"])
    addr = f"{rng.randint(10, 9999)} {rng.choice(TEXT['streets'])}, {rng.choice(TEXT['cities'])}"
    phone = f"({rng.randint(200, 989)}) {rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
    name, is_brand = drug_text(rng, p)
    st = strength_text(rng, p)
    sig = rng.choice(TEXT["sigs"])
    pt = person(rng).upper()
    dr = f"DR. {rng.choice(TEXT['last_names']).upper()}"
    rx = f"Rx# {rng.randint(1000000, 9999999)}"
    qty = f"QTY: {rng.choice([14, 28, 30, 60, 90, 100])}   REFILLS: {rng.randint(0, 5)}"
    date = f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/{rng.choice([2025, 2026])}"
    generic_for = f"GENERIC FOR {rng.choice(p.brands).upper()}" if (p.brands and not is_brand and rng.random() < 0.5) else \
        f"MFR: {rng.choice(TEXT['manufacturers'])}"
    y = 16
    if variant == 0:
        band = rng.choice([(200, 30, 40), (20, 90, 170), (30, 130, 80), (90, 40, 130)])
        d.rectangle([0, 0, W, 86], fill=band)
        cv.text(d, (20, 10), pharm, f_bold, 34, (255, 255, 255))
        cv.text(d, (20, 52), f"{addr}  {phone}", f_reg, 20, (255, 255, 255))
        y = 100
    elif variant == 1:
        for i in range(60):
            if rng.random() < 0.6:
                d.rectangle([20, 40 + i * 7, 110, 40 + i * 7 + rng.randint(2, 5)], fill=ink)
        cv.text(d, (140, 14), pharm + "  " + phone, f_reg, 22, ink)
        y = 50
    x0 = 140 if variant == 1 else 24
    if variant == 2:
        cv.text(d, (x0, y), pt, f_bold, 40, ink)
        y += 56
    cv.text(d, (x0, y), f"{rx}   {date}", f_reg, 22, ink)
    y += 36
    if variant != 2:
        cv.text(d, (x0, y), pt, f_bold, 30, ink)
        y += 46
    size = rng.randint(34, 46)
    if variant == 3:
        cv.text(d, (x0, y + 6), "DRUG:", f_reg, 22, ink)
        nb = cv.text(d, (x0 + 110, y), name, f_bold, cv.fit_size(name, f_bold, W - x0 - 140, 80, size), ink)
        y = nb[3] + 12
        cv.text(d, (x0, y + 6), "STRENGTH:", f_reg, 22, ink)
        sb = cv.text(d, (x0 + 160, y), st, f_bold, size - 4, ink)
        cv.text(d, (sb[2] + 20, y + 6), _form_word(rng, p), f_reg, 24, ink)
        y = sb[3] + 16
    else:
        size = cv.fit_size(name, f_bold, W - x0 - 30, 80, size)
        nw, sw = cv.text_size(name, f_bold, size)[0], cv.text_size(st, f_bold, size)[0]
        nb = cv.text(d, (x0, y), name, f_bold, size, ink)
        if x0 + nw + 14 + sw <= W - 20:
            sb = cv.text(d, (nb[2] + 14, y), st, f_bold, size, ink)
        else:                                              # too long for one line: strength on the next
            sb = cv.text(d, (x0, nb[3] + 8), st, f_bold, size, ink)
        cv.text(d, (sb[2] + 12, sb[1]), _form_word(rng, p), f_reg, int(size * 0.7), ink)
        y = sb[3] + 16
    reading = _med(p, nb, sb, f"{name} {st}")
    cv.text(d, (x0, y), sig, f_reg, 26, ink)
    y += 40
    cv.text(d, (x0, y), qty, f_reg, 22, ink)
    y += 32
    cv.text(d, (x0, y), f"{dr}    {generic_for}", f_reg, 20, ink)
    y += 30
    if rng.random() < 0.7 and y < H - 40:
        cv.text(d, (x0, y), f"DISCARD AFTER {rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/2027", f_reg, 18, ink)
    if rng.random() < 0.6:
        col = rng.choice([(255, 210, 0), (255, 120, 160), (120, 200, 255), (170, 230, 120)])
        wx = W - 230
        d.rectangle([wx, H - 120, W - 10, H - 10], fill=col)
        warn = rng.choice(TEXT["aux_warnings"])
        cv.text(d, (wx + 10, H - 110), warn[:18], f_bold, 20, (0, 0, 0))
        cv.text(d, (wx + 10, H - 80), warn[18:36], f_bold, 20, (0, 0, 0))
    readings = [reading]
    bottle_col = rng.choice([(190, 110, 30), (230, 140, 40), (245, 245, 245), (40, 90, 160)])
    big, bd = cv.new_canvas(W + 80, H + 260, (0, 0, 0, 0))
    cv.rounded(bd, (0, 60, W + 80, H + 260), 30, fill=bottle_col + (235,))
    bd.rectangle([30, 0, W + 50, 70], fill=rng.choice([(250, 250, 250), (230, 230, 230), (40, 120, 200)]) + (255,))
    big.paste(im, (40, 150))
    for r in readings:
        r.box = (r.box[0] + 40, r.box[1] + 150, r.box[2] + 40, r.box[3] + 150)
        r.strength_box = (r.strength_box[0] + 40, r.strength_box[1] + 150, r.strength_box[2] + 40, r.strength_box[3] + 150)
    if rng.random() < 0.7:
        big = cylinder(big, rng.uniform(0.6, 1.0), readings)
    texts = [name, st, sig, pt, pharm]
    return Panel(big, readings, f"pharmacy_label/v{variant}", "pill_label", "pill_bottle", texts=texts,
                 distractors=["patient name", "Rx#", "quantity", "refills", "prescriber", "warning sticker"])


def stock_package(rng: Random, variant: int, catalog: Catalog) -> Panel:
    """Variants: 0 manufacturer bottle, 1 carton front, 2 (held out) blister foil back (repeated print)."""
    p = catalog.pick(rng, "bottle")
    f_bold, f_reg = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    brand = rng.choice(p.brands) if p.brands and rng.random() < 0.6 else None
    count = rng.choice([30, 60, 90, 100, 500, 1000])
    st = strength_text(rng, p)
    readings, texts = [], []
    if variant == 2:
        W, H = 820, 560
        im, d = cv.new_canvas(W, H, (205, 208, 212, 255))
        for i in range(12):
            x, y = 40 + (i % 3) * 260, 30 + (i // 3) * 130
            d.ellipse([x + 60, y + 50, x + 200, y + 110], outline=(170, 172, 176), width=3)
        ink = rng.choice([(20, 60, 140), (150, 20, 30), (20, 20, 20)])
        label = (brand or p.generic).upper()
        for i in range(4):
            y = 20 + i * 135
            nb = cv.text(d, (30 + (i % 2) * 60, y), label, f_bold, 30, ink)
            sb = cv.text(d, (nb[2] + 10, y), st, f_bold, 30, ink)
            if i == 1:
                readings.append(_med(p, nb, sb, f"{label} {st}"))
            cv.text(d, (30 + (i % 2) * 60, y + 40), f"LOT {rng.randint(10000, 99999)}  EXP {rng.randint(1, 12)}/27", f_reg,
                    18, ink)
        texts = [label, st]
        return Panel(im, readings, f"stock_package/v{variant}", "blister", "pill_bottle", texts=texts, flat=True,
                     distractors=["lot", "expiry"])
    W, H = (760, 900) if variant == 1 else (900, 620)
    bgc = rng.choice([(255, 255, 255), (240, 245, 250), (250, 245, 235)])
    im, d = cv.new_canvas(W, H, bgc + (255,))
    stripe = rng.choice([(0, 100, 180), (200, 40, 60), (0, 140, 100), (120, 60, 160), (240, 140, 0)])
    d.rectangle([0, 0, W, 70 if variant == 0 else 120], fill=stripe)
    cv.text(d, (24, 18), f"NDC {rng.randint(10000, 99999)}-{rng.randint(100, 999)}-{rng.randint(10, 99)}", f_reg, 24,
            (255, 255, 255))
    y = 110 if variant == 0 else 170
    if brand:
        bname = brand.title() if rng.random() < 0.5 else brand.upper()
        nb = cv.text(d, (30, y), bname, f_bold, cv.fit_size(bname, f_bold, W - 60, 100, rng.randint(60, 90)), stripe)
        y = nb[3] + 12
        gline = f"({p.generic}) {p.form.split()[-1]}s"
        gb = cv.text(d, (30, y), gline, f_reg, cv.fit_size(gline, f_reg, W - 60, 40, 30), (40, 40, 40))
        y = gb[3] + 14
        name_box, shown = nb, brand
    else:
        nb = cv.text(d, (30, y), p.generic.title(), f_bold, cv.fit_size(p.generic.title(), f_bold, W - 60, 90,
                                                                           rng.randint(46, 70)), (30, 30, 30))
        name_box, shown = nb, p.generic
        y = nb[3] + 14
    sb = cv.text(d, (30, y), st, f_bold, rng.randint(40, 60), stripe)
    readings.append(_med(p, name_box, sb, f"{shown} {st}"))
    y = sb[3] + 20
    cv.text(d, (30, y), f"{count} {p.form.split()[-1].title()}s", f_reg, 30, (40, 40, 40))
    cv.text(d, (30, y + 44), rng.choice(["Rx only", "Rx Only", "Each tablet contains"]), f_reg, 24, (60, 60, 60))
    cv.text(d, (30, H - 50), rng.choice(TEXT["manufacturers"]), f_reg, 24, (60, 60, 60))
    texts = [shown, st]
    return Panel(im, readings, f"stock_package/v{variant}", "stock_bottle" if variant == 0 else "carton", "pill_bottle",
                 texts=texts, flat=variant == 1, distractors=["NDC", "count", "manufacturer"])


def device_label(rng: Random, variant: int, catalog: Catalog) -> Panel:
    """Variants: 0 inhaler canister/boot, 1 insulin or injector pen, 2 (held out) transdermal patch box."""
    pkg = {0: "inhaler", 1: "pen", 2: "patch"}[variant]
    p = catalog.pick(rng, pkg)
    f_bold, f_reg = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    brand = rng.choice(p.brands) if p.brands and rng.random() < 0.7 else None
    st = strength_text(rng, p)
    col = rng.choice([(40, 100, 200), (220, 60, 40), (120, 60, 160), (0, 140, 110), (240, 160, 0), (90, 90, 90)])
    if variant == 1:
        W, H = 1400, 260
        im, d = cv.new_canvas(W, H, (0, 0, 0, 0))
        cv.rounded(d, (0, 20, W, H - 20), 110, fill=(235, 235, 238, 255))
        d.rectangle([W - 300, 20, W - 120, H - 20], fill=col + (255,))
        d.rectangle([W - 120, 50, W, H - 50], fill=(200, 200, 205, 255))
        x, y = 80, 50
    elif variant == 0:
        W, H = 700, 900
        im, d = cv.new_canvas(W, H, (0, 0, 0, 0))
        cv.rounded(d, (100, 0, W - 100, H - 250), 60, fill=(225, 225, 228, 255))
        cv.rounded(d, (60, H - 300, W - 60, H), 50, fill=col + (255,))
        x, y = 130, 120
    else:
        W, H = 820, 620
        im, d = cv.new_canvas(W, H, (250, 250, 250, 255))
        d.rectangle([0, 0, W, 90], fill=col)
        x, y = 30, 130
    readings = []
    ink = (20, 20, 20)
    if brand:
        room = (W - 330 if variant == 1 else W - 2 * x)
        bname = brand.upper() if rng.random() < 0.5 else brand.title()
        nb = cv.text(d, (x, y), bname, f_bold, cv.fit_size(bname, f_bold, room, 70, 56), col if variant != 1 else ink)
        gb = cv.text(d, (x, nb[3] + 10), p.generic, f_reg, cv.fit_size(p.generic, f_reg, room, 40, 30), ink)
        y2, shown = gb[3] + 10, brand
    else:
        room = (W - 330 if variant == 1 else W - 2 * x)
        nb = cv.text(d, (x, y), p.generic.title(), f_bold, cv.fit_size(p.generic.title(), f_bold, room, 64, 50), ink)
        y2, shown = nb[3] + 10, p.generic
    unit_tail = {"inhaler": " per actuation", "pen": "", "patch": ""}[pkg] if rng.random() < 0.5 else ""
    sb = cv.text(d, (x, y2), st + unit_tail, f_bold, 36, ink)
    readings.append(_med(p, nb, sb, f"{shown} {st}"))
    extra = {"inhaler": f"{rng.choice([60, 120, 200])} METERED INHALATIONS", "pen": rng.choice(["3 mL", "KwikPen", "FlexTouch",
                                                                                              "Single-patient-use pen"]),
             "patch": f"{rng.choice([5, 10, 30])} systems | Apply every 72 hours"}[pkg]
    cv.text(d, (x, sb[3] + 12), extra, f_reg, 26, ink)
    return Panel(im, readings, f"device_label/v{variant}", pkg, "pill_bottle", texts=[shown, st], flat=variant == 2)


def med_list(rng: Random, variant: int, catalog: Catalog) -> Panel:
    """Variants: 0 printed table, 1 handwritten list on lined paper, 2 (held out) after-visit summary section."""
    W, H = 900, 1150
    hand = variant == 1
    paper = (255, 255, 255) if not hand else rng.choice([(255, 252, 225), (250, 250, 250), (240, 245, 255)])
    im, d = cv.new_canvas(W, H, paper + (255,))
    f_head, f_row = cv.pick_font(rng, "bold"), cv.pick_font(rng, "hand" if hand else rng.choice(["sans", "mono", "serif"]))
    ink = rng.choice([(20, 30, 120), (20, 20, 20), (60, 20, 20)]) if hand else (20, 20, 20)
    if hand:
        for y in range(120, H, 60):
            d.line([(0, y), (W, y)], fill=(170, 190, 220), width=2)
        d.line([(80, 0), (80, H)], fill=(230, 150, 150), width=2)
    title = rng.choice(["My Medications", "MEDICATION LIST", "Current Medications", "Meds", "Home medications"])
    cv.text(d, (100 if hand else 40, 40), title, f_row if hand else f_head, 44, ink)
    if variant == 2:
        cv.text(d, (40, 100), f"After Visit Summary  -  {person(rng)}  -  DOB {rng.randint(1, 12)}/{rng.randint(1, 28)}/19"
                f"{rng.randint(30, 99)}", cv.pick_font(rng, "sans"), 22, ink)
    n = rng.randint(2, 7)
    seen, products = set(), []
    while len(products) < n:
        pr = catalog.pick(rng)
        if pr.ingredient not in seen:
            seen.add(pr.ingredient)
            products.append(pr)
    readings, texts = [], []
    y = 150 if not hand else 128
    if not hand:
        cv.text(d, (40, y), "Medication", f_head, 26, ink)
        cv.text(d, (470, y), "Dose", f_head, 26, ink)
        cv.text(d, (640, y), "How to take", f_head, 26, ink)
        y += 46
        d.line([(40, y - 6), (W - 40, y - 6)], fill=ink, width=2)
    for pr in products:
        name, _ = drug_text(rng, pr)
        if hand:
            name = name.title() if rng.random() < 0.7 else name.lower()
        st = strength_text(rng, pr).replace(" ", "" if hand and rng.random() < 0.5 else " ")
        sig = rng.choice(["1 daily", "1 tab bid", "twice a day", "at night", "prn", "AM", "1 in morning", "as needed"])
        if hand:
            nb = cv.text(d, (100 + rng.randint(-6, 6), y + rng.randint(0, 8)), name, f_row, rng.randint(36, 44), ink)
            sb = cv.text(d, (nb[2] + 20, nb[1]), st, f_row, rng.randint(34, 42), ink)
            cv.text(d, (sb[2] + 24, nb[1]), sig, f_row, 32, ink)
            y += 60 * (1 + (nb[3] - nb[1] > 55))
        else:
            size = cv.fit_size(name, f_row, 410, 34, 30)
            nb = cv.text(d, (40, y), name, f_row, size, ink)
            sb = cv.text(d, (470, y), st, f_row, 28, ink)
            cv.text(d, (640, y), sig, f_row, 24, ink)
            y += 58
        readings.append(_med(pr, nb, sb, f"{name} {st}"))
        texts += [name, st]
        if y > H - 160:
            break
    if rng.random() < 0.5:
        allergy = rng.choice(TEXT["allergens"])
        ab = cv.text(d, (100 if hand else 40, y + 30), f"Allergies: {allergy.title()}", f_row, 34, ink)
        readings.append(Reading("allergies", allergy.lower(), ab, allergy))
        texts.append(allergy)
    return Panel(im, readings, f"med_list/v{variant}", "med_list_handwritten" if hand else "med_list", "pill_bottle",
                 texts=texts, flat=True, distractors=["sig", "allergy line"])
