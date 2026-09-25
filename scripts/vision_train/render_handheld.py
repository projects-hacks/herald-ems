"""Single-purpose home and field devices: fingertip pulse oximeters, blood-pressure cuffs (arm and wrist),
glucometers and thermometers (oral stick, forehead, ear). Segment LCD, LED and small color screens; °F/°C and
mg/dL / mmol/L; error, HI/LO and memory-average screens that carry no current reading."""
from __future__ import annotations

from random import Random

from . import canvas as cv
from .spec import Panel, Reading
from .values import glucose_display, sample, temp_display

LCD = [(170, 185, 160), (185, 195, 175), (200, 205, 190), (150, 175, 190), (120, 170, 220), (160, 200, 150)]


def _width(s: str, h: float, font_path: str, seg: bool) -> float:
    return cv.seven_seg_width(s, h) + h * 0.2 if seg else cv.text_size(s, font_path, int(h * 1.3))[0]


def fit(s: str, h: float, avail: float, font_path: str, seg: bool) -> float:
    """Digit height, shrunk until the number fits the available width."""
    while h > 8 and _width(s, h, font_path, seg) > avail:
        h *= 0.93
    return h


def _num(d, rng, x, y, h, s, color, off, font_path, seg: bool, avail: float | None = None):
    """A number either in seven-segment style or a font; returns its box. (x, y) = top-left."""
    if avail:
        h = fit(s, h, avail, font_path, seg)
    if seg:
        return cv.seven_seg(d, x, y, h, s, color, off=off, skew=rng.uniform(0, 0.1))
    return cv.text(d, (x, y), s, font_path, int(h * 1.3), color)


def _num_right(d, rng, x_right, y, h, s, color, off, font_path, seg: bool, avail: float | None = None):
    if avail:
        h = fit(s, h, avail, font_path, seg)
    w = _width(s, h, font_path, seg)
    return _num(d, rng, x_right - w, y, h, s, color, off, font_path, seg)


def oximeter(rng: Random, variant: int) -> Panel:
    """Variants: 0 OLED side by side, 1 red LED segments, 2 OLED stacked with pleth, 3 (held out) gray LCD."""
    W, H = 520, 300
    im, d = cv.new_canvas(W + 160, H + 200, (0, 0, 0, 0))
    shell = rng.choice([(30, 30, 35), (220, 220, 225), (40, 90, 170), (200, 40, 60), (60, 160, 120), (240, 180, 40)])
    cv.rounded(d, (0, 0, W + 160, H + 200), 90, fill=shell + (255,))
    ox, oy = 80, 90
    v = sample(rng)
    fp = cv.pick_font(rng, "bold")
    lab = cv.pick_font(rng, "sans")
    readings: list[Reading] = []
    spo2_s, hr_s = str(v.spo2), str(v.hr)
    if variant == 3:
        bg, ink, off = rng.choice(LCD[:3]), (25, 30, 25), None
    else:
        bg, ink, off = (0, 0, 0), None, None
    d.rectangle([ox, oy, ox + W, oy + H], fill=bg)
    c1 = rng.choice([(255, 220, 0), (0, 230, 255), (255, 255, 255), (80, 255, 80)]) if variant != 1 else (255, 40, 30)
    c2 = rng.choice([(0, 230, 255), (80, 255, 80), (255, 255, 255), (255, 220, 0)]) if variant != 1 else (255, 40, 30)
    if variant == 3:
        c1 = c2 = ink
    seg = variant in (1, 3) or rng.random() < 0.3
    spo2_lab = rng.choice(["%SpO2", "SpO2%", "SpO2", "O2%", "SPO2"])
    hr_lab = rng.choice(["PRbpm", "PR bpm", "BPM", "PR/min", "PR"])
    if variant in (0, 1, 3):
        h = H * 0.5
        cv.text(d, (ox + 14, oy + 10), spo2_lab, lab, 26, c1)
        b1 = _num(d, rng, ox + 30, oy + H * 0.32, h, spo2_s, c1, off, fp, seg, avail=W * 0.5 - 50)
        cv.text(d, (ox + W * 0.55, oy + 10), hr_lab, lab, 26, c2)
        b2 = _num(d, rng, ox + W * 0.56, oy + H * 0.32, h, hr_s, c2, off, fp, seg, avail=W * 0.44 - 50)
        if rng.random() < 0.6:
            cv.bars(d, ox + W - 40, oy + 30, 26, H - 60, 8, rng.randint(2, 8), c2, (40, 40, 40))
    else:
        h = H * 0.36
        cv.text(d, (ox + 14, oy + 8), spo2_lab, lab, 22, c1)
        b1 = _num_right(d, rng, ox + W * 0.5, oy + 16, h, spo2_s, c1, off, fp, seg, avail=W * 0.45)
        cv.text(d, (ox + 14, oy + H * 0.52), hr_lab, lab, 22, c2)
        b2 = _num_right(d, rng, ox + W * 0.5, oy + H * 0.55, h, hr_s, c2, off, fp, seg, avail=W * 0.45)
        cv.waveform(d, rng, (ox + W * 0.56, oy + 20, ox + W - 12, oy + H - 20), "pleth", c1, 3)
    readings += [Reading("vitals.spo2", v.spo2, b1, spo2_s), Reading("vitals.hr", v.hr, b2, hr_s)]
    distract = []
    if rng.random() < 0.45:
        pi = f"PI {rng.uniform(0.3, 12):.1f}"
        cv.text(d, (ox + W * 0.3, oy + H - 34), pi, lab, 24, c2 if variant != 3 else ink)
        distract.append(pi)
    cv.battery(d, ox + 12, oy + H - 30, 30, 16, rng.random(), c1 if variant != 3 else ink)
    return Panel(im, readings, f"fingertip_oximeter/v{variant}", "fingertip_oximeter", "monitor", distractors=distract)


def bp_cuff(rng: Random, variant: int) -> Panel:
    """Variants: 0 arm cuff stacked SYS/DIA/PUL, 1 arm cuff SYS|DIA big + pulse small, 2 wrist cuff,
    3 (held out) blue backlit LCD with memory column."""
    wrist = variant == 2
    W, H = (380, 440) if wrist else (560, 520)
    im, d = cv.new_canvas(W + 120, H + (160 if wrist else 320), (0, 0, 0, 0))
    cv.rounded(d, (0, 0, im.width, im.height), 60, fill=rng.choice([(235, 235, 238), (245, 245, 245), (60, 60, 70),
                                                                    (210, 220, 235)]) + (255,))
    ox, oy = 60, 60
    bg = (120, 170, 230) if variant == 3 else rng.choice(LCD)
    d.rectangle([ox, oy, ox + W, oy + H], fill=bg)
    ink = (20, 25, 30)
    off = (bg[0] - 6, bg[1] - 6, bg[2] - 6) if rng.random() < 0.3 else None      # faint unlit segments
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    seg = rng.random() < 0.8
    v = sample(rng, rng.choice(["normal", "hypertensive", "hypertensive", "shock", "brady", "tachy_fever"]))
    screen = rng.choices(["reading", "error", "average"], weights=[0.86, 0.07, 0.07])[0]
    readings: list[Reading] = []
    notes = []
    if screen == "error":
        code = rng.choice(["E 1", "E 2", "Err", "E 5", "EE"])
        _num(d, rng, ox + W * 0.2, oy + H * 0.3, H * 0.3, code.replace(" ", ""), ink, off, fp, seg)
        notes.append("error screen: no reading")
    else:
        rows = [("SYS", "mmHg", str(v.sbp), "vitals.sbp", v.sbp), ("DIA", "mmHg", str(v.dbp), "vitals.dbp", v.dbp),
                ("PUL", "/min", str(v.hr), "vitals.hr", v.hr)]
        if variant == 1:
            h = H * 0.3
            cv.text(d, (ox + 16, oy + 10), rng.choice(["SYS", "SYST", "Systolic"]), lab, 22, ink)
            b1 = _num_right(d, rng, ox + W * 0.48, oy + 50, h, rows[0][2], ink, off, fp, seg, avail=W * 0.45)
            cv.text(d, (ox + W * 0.54, oy + 10), rng.choice(["DIA", "DIAST", "Diastolic"]), lab, 22, ink)
            b2 = _num_right(d, rng, ox + W - 16, oy + 50, h, rows[1][2], ink, off, fp, seg, avail=W * 0.45)
            cv.text(d, (ox + 16, oy + H * 0.72), rng.choice(["PULSE/min", "PUL", "Pulse /min"]), lab, 22, ink)
            b3 = _num_right(d, rng, ox + W - 16, oy + H * 0.62, h * 0.55, rows[2][2], ink, off, fp, seg)
            boxes = [b1, b2, b3]
        else:
            rh = H * (0.3 if variant != 3 else 0.28)
            boxes = []
            x_right = ox + W - (130 if variant == 3 else 20)
            for i, (lb, unit, s, _, _) in enumerate(rows):
                y = oy + 16 + i * rh
                cv.text(d, (ox + 12, y + 4), rng.choice([lb, lb.title(), lb + " " + unit]), lab, 20, ink)
                boxes.append(_num_right(d, rng, x_right, y, rh * (0.78 if i < 2 else 0.55), s, ink, off, fp, seg,
                                        avail=x_right - ox - 110))
            if variant == 3:
                for j in range(3):
                    cv.text(d, (ox + W - 110, oy + 20 + j * 34), f"M{j + 1} {rng.randint(100, 160)}/{rng.randint(60, 95)}",
                            lab, 18, ink)
        if screen == "average":
            cv.text(d, (ox + 12, oy + H - 30), rng.choice(["AVG", "Avg of 3", "AVERAGE", "MEM AVG"]), fp, 26, ink)
            notes.append("memory average: not the current reading")
        else:
            readings += [Reading(r[3], r[4], b, r[2]) for r, b in zip(rows, boxes)]
    if rng.random() < 0.7:
        cv.text(d, (ox + W - 12, oy + H - 28), f"{rng.randint(1, 12)}/{rng.randint(1, 28)} {rng.randint(0, 23)}:"
                f"{rng.randint(0, 59):02d}", lab, 18, ink, anchor="ra")
    if rng.random() < 0.5:
        cv.heart(d, ox + W * 0.5, oy + H - 20, 10, ink)
    return Panel(im, readings, f"bp_cuff/v{variant}", "bp_cuff_wrist" if wrist else "bp_cuff", "monitor",
                 distractors=["memory", "date/time"], notes=notes)


def glucometer(rng: Random, variant: int) -> Panel:
    """Variants: 0 segment LCD, 1 color screen, 2 rounded meter with strip port, 3 (held out) wide landscape LCD."""
    W, H = (520, 300) if variant == 3 else (400, 380)
    im, d = cv.new_canvas(W + 120, H + 330, (0, 0, 0, 0))
    cv.rounded(d, (0, 0, im.width, im.height), 70 if variant == 2 else 40,
               fill=rng.choice([(30, 30, 35), (230, 230, 235), (60, 110, 180), (170, 40, 90), (90, 90, 95)]) + (255,))
    ox, oy = 60, 70
    color_screen = variant == 1
    bg = (10, 10, 10) if color_screen else rng.choice(LCD)
    ink = (255, 255, 255) if color_screen else (20, 25, 25)
    d.rectangle([ox, oy, ox + W, oy + H], fill=bg)
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    seg = not color_screen and rng.random() < 0.85
    mmol = rng.random() < 0.28
    v = sample(rng, rng.choice(["normal", "hypoglycemic", "hyperglycemic", "hyperglycemic", "hypoglycemic"]))
    screen = rng.choices(["reading", "HI", "LO", "error"], weights=[0.86, 0.05, 0.04, 0.05])[0]
    readings, notes = [], []
    h = H * 0.42
    if screen == "reading":
        shown, mgdl = glucose_display(rng, v.glucose, mmol)
        b = _num_right(d, rng, ox + W - 30, oy + H * 0.25, h, shown, ink, None, fp, seg, avail=W - 60)
        readings.append(Reading("vitals.glucose", mgdl, b, shown + (" mmol/L" if mmol else " mg/dL")))
    else:
        s = {"HI": "HI", "LO": "LO", "error": rng.choice(["E-3", "Er4", "E-1"])}[screen]
        _num_right(d, rng, ox + W - 30, oy + H * 0.25, h, s.replace("-", "-"), ink, None, fp, seg)
        notes.append(f"{screen}: no number to read")
    cv.text(d, (ox + W - 20, oy + H * 0.25 + h + 12), "mmol/L" if mmol else "mg/dL", lab, 26, ink, anchor="ra")
    cv.text(d, (ox + 14, oy + 12), f"{rng.randint(1, 12)}-{rng.randint(1, 28)}  {rng.randint(0, 23)}:{rng.randint(0, 59):02d}",
            lab, 22, ink)
    if rng.random() < 0.4:
        cv.text(d, (ox + 14, oy + H - 34), rng.choice(["AC", "PC", "MEM", "7d avg 142", "14d avg 9.1"]), lab, 22, ink)
    if variant == 2:
        d.rectangle([im.width / 2 - 30, im.height - 40, im.width / 2 + 30, im.height], fill=(15, 15, 15, 255))
    return Panel(im, readings, f"glucometer/v{variant}", "glucometer", "monitor",
                 distractors=["date/time", "memory"], notes=notes)


def thermometer(rng: Random, variant: int) -> Panel:
    """Variants: 0 oral stick, 1 forehead gun backlit, 2 ear thermometer, 3 (held out) round-window stick."""
    fahr = rng.random() < 0.5
    v = sample(rng, rng.choice(["normal", "tachy_fever", "tachy_fever", "hypothermic", "normal"]))
    screen = rng.choices(["reading", "Lo", "Hi", "Err"], weights=[0.88, 0.04, 0.03, 0.05])[0]
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    seg = rng.random() < 0.85
    if variant in (0, 3):
        W, H = 900, 200
        im, d = cv.new_canvas(W, H, (0, 0, 0, 0))
        cv.rounded(d, (0, 20, W, H - 20), 70, fill=rng.choice([(245, 245, 245), (120, 180, 230), (250, 190, 200)]) + (255,))
        d.polygon([(W - 20, H / 2 - 12), (W, H / 2), (W - 20, H / 2 + 12)], fill=(190, 190, 195, 255))
        win = (120, 45, 520, H - 45)
        bg = rng.choice(LCD[:3])
        if variant == 3:
            d.ellipse(win, fill=bg)
        else:
            d.rectangle(win, fill=bg)
    else:
        W, H = 520, 560
        im, d = cv.new_canvas(W, H, (0, 0, 0, 0))
        cv.rounded(d, (0, 0, W, H), 120 if variant == 2 else 50, fill=rng.choice([(250, 250, 250), (230, 235, 245),
                                                                                  (40, 40, 45)]) + (255,))
        win = (70, 70, W - 70, 330)
        bg = rng.choice([(120, 220, 120), (255, 170, 60), (120, 200, 255), (230, 230, 220)]) if variant == 1 else \
            rng.choice(LCD)
        d.rectangle(win, fill=bg)
    ink = (20, 25, 30)
    x0, y0, x1, y1 = win
    h = (y1 - y0) * 0.55
    readings, notes = [], []
    if screen == "reading":
        shown, c = temp_display(rng, v.temp_c, fahr)
        b = _num_right(d, rng, x1 - (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.2, h, shown, ink, None, fp, seg,
                       avail=(x1 - x0) * 0.72)
        readings.append(Reading("vitals.temp", c, b, shown + ("°F" if fahr else "°C")))
    else:
        _num_right(d, rng, x1 - (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.2, h, screen.replace("Err", "Err"), ink, None, fp, seg)
        notes.append(f"{screen}: no reading")
    cv.text(d, (x1 - 10, y0 + (y1 - y0) * 0.25), "°F" if fahr else "°C", lab, int(h * 0.45), ink, anchor="ra")
    if variant in (1, 2) and rng.random() < 0.7:
        cv.text(d, (x0 + 12, y0 + 10), rng.choice(["BODY", "MEM 07", "EAR", "HEAD", "LAST 98.2"]), lab, 24, ink)
    return Panel(im, readings, f"thermometer/v{variant}", "thermometer", "monitor", notes=notes)
