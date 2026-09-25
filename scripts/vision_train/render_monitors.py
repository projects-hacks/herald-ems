"""Multi-parameter monitors: bedside/transport monitors, defibrillator monitors, AED screens and handheld
capnographs. Each layout variant is its own geometry; labels, colors, fonts, which parameters are on and the
distractors (alarm limits, MAP, previous NIBP, clocks, energy, shock counts, ST/PI/PVC numbers) are random."""
from __future__ import annotations

from random import Random

from . import canvas as cv
from .spec import Panel, Reading
from .values import Vitals, sample, temp_display

LABELS = {"hr": ["HR", "Heart Rate", "HR bpm", "PULSE", "ECG HR", "HR/min"],
          "spo2": ["SpO2", "%SpO2", "SAT", "O2 SAT", "SpO2 %"],
          "nibp": ["NIBP", "NBP", "BP", "NIBP mmHg", "Cuff"],
          "rr": ["RR", "RESP", "Resp", "awRR", "BR", "RR rpm"],
          "temp": ["TEMP", "T1", "Temp", "T core", "Tmp"],
          "etco2": ["EtCO2", "CO2", "ETCO2", "etCO2 mmHg"]}
DARK = [{"hr": (0, 230, 90), "spo2": (0, 210, 255), "nibp": (255, 255, 255), "rr": (255, 230, 0),
         "temp": (255, 140, 200), "etco2": (255, 235, 90)},
        {"hr": (80, 255, 80), "spo2": (255, 255, 0), "nibp": (255, 80, 80), "rr": (255, 255, 255),
         "temp": (200, 200, 255), "etco2": (120, 200, 255)},
        {"hr": (255, 200, 0), "spo2": (0, 255, 255), "nibp": (255, 120, 0), "rr": (160, 255, 160),
         "temp": (255, 255, 255), "etco2": (255, 255, 255)}]


def _metrics(rng: Random, v: Vitals, fahrenheit: bool, allow: tuple[str, ...]) -> dict[str, tuple[str, object]]:
    """Which parameters show a number, and the printed text -> canonical value. Some show '---' (no signal)."""
    out = {}
    for m in allow:
        if m != "hr" and rng.random() < 0.18:
            continue                                   # parameter not configured on this monitor
        if m == "hr":
            out[m] = (str(v.hr), v.hr)
        elif m == "spo2":
            out[m] = (str(v.spo2), v.spo2)
        elif m == "nibp":
            out[m] = (f"{v.sbp}/{v.dbp}", (v.sbp, v.dbp))
        elif m == "rr":
            out[m] = (str(v.rr), v.rr)
        elif m == "temp":
            shown, c = temp_display(rng, v.temp_c, fahrenheit)
            out[m] = (shown, c)
        elif m == "etco2":
            out[m] = (str(v.etco2), v.etco2)
        if m != "hr" and rng.random() < 0.07:
            out[m] = ("---", None)                     # no signal: nothing to read
    return out


KEY = {"hr": "vitals.hr", "spo2": "vitals.spo2", "rr": "vitals.rr", "temp": "vitals.temp", "etco2": "vitals.etco2"}


def _tile(d, rng, x, y, w, h, m, shown, value, color, fonts, fahrenheit, limits=True) -> list[Reading]:
    """One numeric tile: label, big value, unit, alarm limits. Returns the readings it shows."""
    lab = rng.choice(LABELS[m])
    lsz = max(12, int(h * rng.uniform(0.13, 0.2)))
    cv.text(d, (x + 8, y + 4), lab, fonts["label"], lsz, color)
    unit = {"hr": "bpm", "spo2": "%", "nibp": "mmHg", "rr": "rpm", "temp": "°F" if fahrenheit else "°C",
            "etco2": "mmHg"}[m]
    if rng.random() < 0.7 or m == "temp":            # a temperature always shows its unit (°C/°F decides the value)
        cv.text(d, (x + w - 8, y + 4), unit, fonts["label"], int(lsz * 0.85), color, anchor="ra")
    if limits and m in ("hr", "spo2", "rr", "etco2") and rng.random() < 0.7:
        hi, lo = {"hr": (120, 50), "spo2": (100, 90), "rr": (30, 8), "etco2": (50, 25)}[m]
        hi, lo = hi + rng.choice([0, 0, 10, -10]), lo + rng.choice([0, 0, 5, -5])
        sz = int(lsz * 0.8)
        fmt = rng.choice(["stack", "hilo"])
        if fmt == "stack":
            cv.text(d, (x + 8, y + h * 0.42), str(hi), fonts["label"], sz, color)
            cv.text(d, (x + 8, y + h * 0.42 + sz * 1.3), str(lo), fonts["label"], sz, color)
        else:
            cv.text(d, (x + 8, y + h - sz * 1.4), f"HI {hi}  LO {lo}", fonts["label"], sz, color)
    vx0, vx1 = x + w * 0.28, x + w - 8
    vy0, vy1 = y + h * 0.22, y + h * 0.92
    if m == "nibp" and shown != "---":
        sbp, dbp = value
        s_sbp, s_dbp = str(sbp), str(dbp)
        size = cv.fit_size(f"{s_sbp}/{s_dbp}", fonts["value"], (vx1 - vx0), (vy1 - vy0) * 0.62)
        b1 = cv.text(d, (vx0, vy0), s_sbp, fonts["value"], size, color)
        b2 = cv.text(d, (b1[2] + 2, vy0), "/", fonts["value"], size, color)
        b3 = cv.text(d, (b2[2] + 2, vy0), s_dbp, fonts["value"], size, color)
        if rng.random() < 0.8:
            cv.text(d, (vx0, b1[3] + 6), f"({round((sbp + 2 * dbp) / 3)})", fonts["label"], int(size * 0.45), color)
        if rng.random() < 0.6:
            cv.text(d, (vx1, y + 4 + lsz * 1.2), f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
                    fonts["label"], int(lsz * 0.8), color, anchor="ra")
        return [Reading("vitals.sbp", sbp, b1, s_sbp), Reading("vitals.dbp", dbp, b3, s_dbp)]
    size = cv.fit_size(shown, fonts["value"], vx1 - vx0, vy1 - vy0)
    b = cv.text(d, (vx1, vy1), shown, fonts["value"], size, color, anchor="rd")
    if value is None or m not in KEY:
        return []
    return [Reading(KEY[m], value, b, shown)]


def _fonts(rng: Random) -> dict:
    return {"label": cv.pick_font(rng, "sans"), "value": cv.pick_font(rng, rng.choice(["bold", "bold", "sans"]))}


def bedside(rng: Random, variant: int) -> Panel:
    """Variants: 0 waves left + column right, 1 waves top + tiles bottom, 2 light theme grid, 3 big-number grid,
    4 numbers left + waves right (held out)."""
    W, H = rng.choice([(1280, 800), (1200, 900), (1366, 768)])
    light = variant == 2
    bg = (245, 245, 240) if light else rng.choice([(0, 0, 0), (8, 12, 28), (18, 18, 18), (0, 16, 24)])
    im, d = cv.new_canvas(W + 60, H + 60, (60, 62, 66, 255))
    cv.rounded(d, (10, 10, W + 50, H + 50), 18, fill=rng.choice([(70, 72, 78), (200, 200, 205), (40, 40, 44)]) + (255,))
    d.rectangle([30, 30, W + 30, H + 30], fill=bg)
    pal = rng.choice(DARK)
    if light:
        pal = {k: tuple(int(c * 0.55) for c in col) for k, col in pal.items()}
    fonts = _fonts(rng)
    v = sample(rng)
    fahr = rng.random() < 0.35
    mets = _metrics(rng, v, fahr, ("hr", "spo2", "nibp", "rr", "temp", "etco2"))
    ox, oy = 30, 30
    txt = (40, 40, 40) if light else (220, 220, 220)
    # header: bed, patient type, clock, battery
    cv.text(d, (ox + 12, oy + 8), rng.choice(["BED 07", "Bed 12", "ICU-3", "ADULT", "Rm 214", "MED 4"]),
            fonts["label"], 22, txt)
    cv.text(d, (ox + W - 90, oy + 8), f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}", fonts["label"], 22, txt)
    cv.battery(d, ox + W - 150, oy + 12, 34, 16, rng.random(), txt)
    readings: list[Reading] = []
    names = list(mets)
    if variant in (0, 4):
        col_w = W * rng.uniform(0.3, 0.38)
        cx = ox + (W - col_w if variant == 0 else 0)
        wx = ox + (0 if variant == 0 else col_w)
        th = (H - 40) / max(3, len(names))
        for i, m in enumerate(names):
            d.line([(cx, oy + 40 + i * th), (cx + col_w, oy + 40 + i * th)], fill=(90, 90, 90), width=1)
            readings += _tile(d, rng, cx, oy + 40 + i * th, col_w, th, m, *mets[m], pal[m], fonts, fahr)
        for i, (kind, m) in enumerate([("ecg", "hr"), ("pleth", "spo2"), ("resp", "rr"), ("co2", "etco2")][:3]):
            wh = (H - 60) / 3
            cv.waveform(d, rng, (wx + 20, oy + 50 + i * wh, wx + W - col_w - 20, oy + 40 + (i + 1) * wh), kind, pal[m])
            cv.text(d, (wx + 24, oy + 44 + i * wh), rng.choice(["II", "Pleth", "Resp", "I", "aVR"]), fonts["label"], 18, pal[m])
    else:
        big = variant == 3
        wave_h = 0 if big else H * rng.uniform(0.35, 0.45)
        if not big:
            for i, (kind, m) in enumerate([("ecg", "hr"), ("pleth", "spo2")]):
                cv.waveform(d, rng, (ox + 20, oy + 40 + i * wave_h / 2, ox + W - 20, oy + 40 + (i + 1) * wave_h / 2),
                            kind, pal[m])
        cols = 3 if (big or len(names) > 4) else len(names)
        rows = (len(names) + cols - 1) // cols
        tw, th = W / cols, (H - 50 - wave_h) / rows
        for i, m in enumerate(names):
            tx, ty = ox + (i % cols) * tw, oy + 45 + wave_h + (i // cols) * th
            d.rectangle([tx + 3, ty + 3, tx + tw - 3, ty + th - 3], outline=(110, 110, 110), width=1)
            readings += _tile(d, rng, tx + 3, ty + 3, tw - 6, th - 6, m, *mets[m], pal[m], fonts, fahr)
    # distractor strip: previous NIBP readings / ST values
    extra = rng.choice(["ST-II 0.1", "PVC 0", "PI 3.2", "SpHb 12.4", "ST-V -0.2", "ARR ON"])
    cv.text(d, (ox + 12, oy + H - 28), extra + f"   Prev {rng.randint(100, 150)}/{rng.randint(60, 90)}",
            fonts["label"], 18, txt)
    return Panel(im, readings, f"bedside_monitor/v{variant}", "bedside_monitor", "monitor",
                 distractors=["alarm limits", "MAP", "clock", "previous NIBP", extra])


def defib(rng: Random, variant: int) -> Panel:
    """Defibrillator monitor. Variants: 0 black with energy bar, 1 gray body orange text, 2 compact (held out)."""
    W, H = (1000, 700) if variant != 2 else (820, 640)
    body = rng.choice([(40, 40, 40), (230, 120, 20), (90, 90, 95), (200, 30, 30)])
    im, d = cv.new_canvas(W + 160, H + 120, (0, 0, 0, 0))
    cv.rounded(d, (0, 0, W + 160, H + 120), 30, fill=body + (255,))
    bg = (0, 0, 0) if variant != 1 else (25, 25, 25)
    d.rectangle([80, 40, 80 + W, 40 + H], fill=bg)
    fonts = _fonts(rng)
    pal = rng.choice(DARK)
    if variant == 1:
        pal = {k: rng.choice([(255, 170, 0), (255, 255, 255), (0, 255, 120)]) for k in pal}
    v = sample(rng)
    mets = _metrics(rng, v, False, ("hr", "spo2", "nibp", "etco2", "rr"))
    ox, oy = 80, 40
    energy = rng.choice([120, 150, 200, 200, 270, 360])
    top = f"{rng.choice(['PADS', 'PADDLES', 'LEAD II'])}   {energy}J   Shocks: {rng.randint(0, 4)}"
    cv.text(d, (ox + 14, oy + 10), top, fonts["label"], 26, (255, 255, 255))
    cv.text(d, (ox + W - 14, oy + 10), f"{rng.randint(0, 1):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}",
            fonts["label"], 26, (255, 255, 255), anchor="ra")
    cv.waveform(d, rng, (ox + 10, oy + 60, ox + W * 0.62, oy + H * 0.45), "ecg", pal["hr"], 3)
    readings: list[Reading] = []
    names = list(mets)
    col_x = ox + W * 0.64
    th = (H - 60) / max(3, len(names))
    for i, m in enumerate(names):
        readings += _tile(d, rng, col_x, oy + 55 + i * th, W * 0.35, th, m, *mets[m], pal[m], fonts, False)
    cv.text(d, (ox + 14, oy + H - 40), rng.choice(["CHARGE", "SYNC OFF", "PACER 70 ppm", "CPR TIMER 01:12",
                                                   "Analyze"]), fonts["label"], 26, (255, 255, 0))
    return Panel(im, readings, f"defib_monitor/v{variant}", "defib_monitor", "monitor",
                 distractors=[f"{energy}J", "shock count", "event timer"])


def aed(rng: Random, variant: int) -> Panel:
    """AED screen. Variants: 0 prompts only (no vitals: a negative), 1 prompts + HR, 2 (held out) prompts + HR,
    status bar at the bottom."""
    W, H = 760, 520
    im, d = cv.new_canvas(W + 120, H + 200, (0, 0, 0, 0))
    cv.rounded(d, (0, 0, W + 120, H + 200), 40, fill=rng.choice([(250, 200, 0), (30, 120, 60), (240, 240, 235)]) + (255,))
    d.rectangle([60, 50, 60 + W, 50 + H], fill=rng.choice([(0, 0, 0), (10, 10, 40), (230, 235, 230)]))
    light = im.getpixel((70, 60))[0] > 128
    fg = (20, 20, 20) if light else (255, 255, 255)
    fonts = _fonts(rng)
    prompt = rng.choice(["SHOCK ADVISED", "NO SHOCK ADVISED", "START CPR", "ANALYZING", "PUSH FLASHING BUTTON",
                         "STAND CLEAR", "CHECK PADS"])
    y_pr = 50 + H * (0.62 if variant == 2 else 0.1)
    cv.text(d, (60 + W / 2, y_pr), prompt, fonts["value"], 44, fg, anchor="ma")
    cv.text(d, (80, 50 + H * 0.35), f"Shocks {rng.randint(0, 5)}   {rng.choice([150, 200, 360])} J",
            fonts["label"], 32, fg)
    cv.text(d, (60 + W - 20, 50 + H * 0.35), f"{rng.randint(0, 20):02d}:{rng.randint(0, 59):02d}", fonts["label"], 32,
            fg, anchor="ra")
    readings: list[Reading] = []
    if variant in (1, 2):
        v = sample(rng, rng.choice(["tachy_fever", "brady", "shock", "normal"]))
        lab = rng.choice(["HR", "HR bpm", "Pulse"])
        y = 50 + H * (0.15 if variant == 2 else 0.55)
        cv.text(d, (80, y), lab, fonts["label"], 34, fg)
        b = cv.text(d, (80 + 140, y - 10), str(v.hr), fonts["value"], 90, fg)
        readings.append(Reading("vitals.hr", v.hr, b, str(v.hr)))
    cv.waveform(d, rng, (70, 50 + H * 0.78, 60 + W - 10, 50 + H - 10), "ecg", fg, 2)
    return Panel(im, readings, f"aed/v{variant}", "aed", "monitor", distractors=["energy", "shock count", "timer"])


def capnograph(rng: Random, variant: int) -> Panel:
    """Handheld capnograph / pulse-ox combo. Variants: 0 color screen, 1 (held out) mono LCD with segments."""
    W, H = 520, 640
    im, d = cv.new_canvas(W + 80, H + 260, (0, 0, 0, 0))
    cv.rounded(d, (0, 0, W + 80, H + 260), 50, fill=rng.choice([(40, 60, 90), (230, 230, 230), (30, 30, 30)]) + (255,))
    v = sample(rng, rng.choice(["normal", "hypoxic", "shock", "brady", "hyperglycemic"]))
    readings: list[Reading] = []
    fonts = _fonts(rng)
    ox, oy = 40, 40
    if variant == 0:
        d.rectangle([ox, oy, ox + W, oy + H], fill=(0, 0, 0))
        rows = [("etco2", str(v.etco2), (255, 255, 0)), ("rr", str(v.rr), (255, 255, 255)),
                ("spo2", str(v.spo2), (0, 255, 255)), ("hr", str(v.hr), (0, 255, 0))]
        rng.shuffle(rows)
        rh = H * 0.7 / 4
        for i, (m, s, col) in enumerate(rows):
            y = oy + 10 + i * rh
            cv.text(d, (ox + 12, y + 8), rng.choice(LABELS[m]), fonts["label"], 26, col)
            b = cv.text(d, (ox + W - 20, y + rh - 6), s, fonts["value"], int(rh * 0.8), col, anchor="rd")
            readings.append(Reading(KEY[m], int(s), b, s))
        cv.waveform(d, rng, (ox + 10, oy + H * 0.75, ox + W - 10, oy + H - 10), "co2", (255, 255, 0), 3)
    else:
        lcd = rng.choice([(170, 185, 160), (190, 200, 180)])
        d.rectangle([ox, oy, ox + W, oy + H], fill=lcd)
        ink = (30, 35, 30)
        rows = [("etco2", str(v.etco2)), ("rr", str(v.rr)), ("spo2", str(v.spo2)), ("hr", str(v.hr))]
        rh = H / 4
        for i, (m, s) in enumerate(rows):
            y = oy + i * rh
            cv.text(d, (ox + 12, y + 10), rng.choice(LABELS[m]), fonts["label"], 24, ink)
            dh = rh * 0.62
            x = ox + W - 30 - cv.seven_seg_width(s, dh)
            b = cv.seven_seg(d, x, y + rh * 0.25, dh, s, ink, off=(lcd[0] - 12, lcd[1] - 10, lcd[2] - 12))
            readings.append(Reading(KEY[m], int(s), b, s))
    return Panel(im, readings, f"capnograph/v{variant}", "capnograph", "monitor", distractors=["waveform"])
