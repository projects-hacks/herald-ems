"""Electronic displays: bedside and defibrillator monitors, fingertip oximeters, BP cuffs, glucometers, and two
distractor displays (thermostat, bedside clock). Each renderer takes the item spec and returns (image, fields),
where `fields` maps a vocabulary key (or a named region) to its box, for targeted occlusion."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from .primitives import fit, rounded_panel, seven_segment, text

THEMES = {
    "dark": {"bg": (6, 8, 12), "grid": (35, 38, 45), "hr": (60, 230, 90), "spo2": (70, 200, 255),
             "nibp": (235, 235, 235), "rr": (250, 220, 60), "temp": (255, 150, 60), "label": (170, 175, 185),
             "bar": (30, 34, 44)},
    "light": {"bg": (240, 242, 245), "grid": (205, 208, 214), "hr": (20, 140, 50), "spo2": (0, 110, 190),
              "nibp": (180, 30, 40), "rr": (150, 110, 0), "temp": (190, 80, 0), "label": (70, 75, 85),
              "bar": (215, 220, 228)},
}


def _wave(draw, box, kind: str, rate: float, color, width: int = 3):
    """A plausible-looking trace (ECG, pleth or respiration) across `box`; rate in cycles per minute."""
    x0, y0, x1, y1 = box
    mid, amp = (y0 + y1) / 2, (y1 - y0) * 0.42
    period = max(40.0, (x1 - x0) * 60.0 / (rate * 6.0))    # 6 s sweep
    pts = []
    for x in range(int(x0), int(x1), 2):
        p = ((x - x0) % period) / period
        if kind == "ecg":
            v = (0.15 * math.exp(-((p - 0.18) / 0.04) ** 2) - 0.12 * math.exp(-((p - 0.30) / 0.01) ** 2)
                 + 1.0 * math.exp(-((p - 0.33) / 0.012) ** 2) - 0.25 * math.exp(-((p - 0.36) / 0.012) ** 2)
                 + 0.25 * math.exp(-((p - 0.60) / 0.06) ** 2))
        elif kind == "pleth":
            v = 0.9 * math.exp(-((p - 0.25) / 0.10) ** 2) + 0.35 * math.exp(-((p - 0.55) / 0.08) ** 2) - 0.3
        else:
            v = 0.6 * math.sin(2 * math.pi * p)
        pts.append((x, mid - amp * v))
    draw.line(pts, fill=color, width=width)


def _param(draw, x, y, w, h, label, value, color, theme, limits=None, unit="", big=110):
    """One parameter tile: label top-left, big value, optional alarm limits (small numbers) on the right."""
    draw.rectangle([x, y, x + w, y + h], outline=theme["grid"], width=2)
    text(draw, (x + 14, y + 10), label, "sans_bold", 26, color)
    if unit:
        text(draw, (x + 14, y + 42), unit, "sans", 20, theme["label"])
    if limits:
        text(draw, (x + 14, y + 84), str(limits[0]), "sans", 20, theme["label"])
        text(draw, (x + 14, y + 110), str(limits[1]), "sans", 20, theme["label"])
    return text(draw, (x + w - 20, y + h - 12), value, "sans_bold", big, color, anchor="rd")


def bedside_monitor(spec: dict, cfg: dict, rng: random.Random):
    v, theme = spec["values"], THEMES[spec.get("style", "dark")]
    W, H = 1280, 800
    img = rounded_panel((W + 80, H + 80), 30, (70, 72, 78, 255))
    scr = Image.new("RGB", (W, H), theme["bg"])
    d = ImageDraw.Draw(scr)
    d.rectangle([0, 0, W, 44], fill=theme["bar"])
    text(d, (16, 8), "BED 4   ADULT   PACED: OFF", "sans_bold", 24, theme["label"])
    text(d, (W - 16, 8), "14:32", "sans_bold", 24, theme["label"], anchor="ra")
    lanes = [("II", "ecg", v.get("vitals.hr", 80), theme["hr"]), ("Pleth", "pleth", v.get("vitals.hr", 80), theme["spo2"]),
             ("Resp", "resp", v.get("vitals.rr", 16), theme["rr"])]
    for i, (lab, kind, rate, col) in enumerate(lanes):
        y = 70 + i * 160
        text(d, (12, y), lab, "sans", 22, col)
        _wave(d, (60, y + 10, 800, y + 140), kind, rate, col)
    fields, x, w, y, h = {}, 820, 450, 56, 0
    tiles = [("vitals.hr", "HR", str(v.get("vitals.hr", "")), "hr", (120, 50), "bpm"),
             ("vitals.spo2", "SpO2", str(v.get("vitals.spo2", "")), "spo2", (100, 90), "%")]
    for key, lab, val, col, lim, unit in tiles:
        if key in v:
            fields[key] = _param(d, x, y, w, 170, lab, val, theme[col], theme, lim, unit, big=120)
            y += 180
    if "vitals.sbp" in v:
        sbp, dbp = v["vitals.sbp"], v["vitals.dbp"]
        d.rectangle([x, y, x + w, y + 170], outline=theme["grid"], width=2)
        text(d, (x + 14, y + 10), "NIBP  mmHg", "sans_bold", 26, theme["nibp"])
        text(d, (x + w - 14, y + 12), "Man 14:25", "sans", 20, theme["label"], anchor="ra")
        bp = f"{sbp}/{dbp}"
        b = text(d, (x + 20, y + 150), bp, "sans_bold", fit(d, bp, "sans_bold", 88, w - 150), theme["nibp"], anchor="ld")
        text(d, (x + w - 16, y + 150), f"({round((sbp + 2 * dbp) / 3)})", "sans", 34, theme["nibp"], anchor="rd")
        fields["vitals.sbp"] = fields["vitals.dbp"] = b
        y += 180
    small = []
    if "vitals.rr" in v:
        small.append(("vitals.rr", "RR", str(v["vitals.rr"]), theme["rr"], "rpm"))
    if "vitals.temp" in v:
        c = v["vitals.temp"]
        shown = f"{c:.1f}" if spec.get("temp_unit", "C") == "C" else f"{c * 9 / 5 + 32:.1f}"
        small.append(("vitals.temp", "Temp", shown, theme["temp"], "°" + spec.get("temp_unit", "C")))
    sw = w // max(1, len(small))
    for i, (key, lab, val, col, unit) in enumerate(small):
        fields[key] = _param(d, x + i * sw, y, sw, min(170, H - y - 10), lab, val, col, theme, None, unit, big=66)
    # lower-left: event/status text (numbers that are not vitals)
    text(d, (16, H - 40), "Alarms: ON    Vol 5    ST-II 0.1 mm", "sans", 22, theme["label"])
    img.paste(scr, (40, 40))
    return img, {k: (b[0] + 40, b[1] + 40, b[2] + 40, b[3] + 40) for k, b in fields.items()}


def defib_monitor(spec: dict, cfg: dict, rng: random.Random):
    v = spec["values"]
    W, H = 1100, 720
    body = rounded_panel((W + 260, H + 180), 40, (58, 60, 62, 255))
    bd = ImageDraw.Draw(body)
    for i in range(4):                                                  # soft keys under the screen
        bd.rounded_rectangle([150 + i * 260, H + 110, 330 + i * 260, H + 160], 10, fill=(90, 92, 96))
    text(bd, (130 + W / 2, 40), "MONITOR / DEFIBRILLATOR", "sans_bold", 30, (200, 200, 200), anchor="ma")
    scr = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(scr)
    f = {}
    text(d, (20, 16), "HR", "sans_bold", 34, (60, 230, 90))
    f["vitals.hr"] = text(d, (20, 60), str(v["vitals.hr"]), "sans_bold", 150, (60, 230, 90))
    text(d, (420, 16), "SpO2 %", "sans_bold", 34, (70, 200, 255))
    f["vitals.spo2"] = text(d, (420, 60), str(v["vitals.spo2"]), "sans_bold", 150, (70, 200, 255))
    text(d, (780, 16), "EtCO2 mmHg", "sans_bold", 30, (250, 220, 60))
    text(d, (780, 60), str(spec.get("etco2", 38)), "sans_bold", 96, (250, 220, 60))
    text(d, (780, 190), "RR", "sans_bold", 30, (250, 220, 60))
    f["vitals.rr"] = text(d, (860, 180), str(v["vitals.rr"]), "sans_bold", 80, (250, 220, 60))
    _wave(d, (20, 300, W - 20, 440), "ecg", v["vitals.hr"], (60, 230, 90))
    text(d, (20, 290), "II  x1.0", "sans", 22, (60, 230, 90))
    _wave(d, (20, 450, W - 20, 540), "pleth", v["vitals.hr"], (70, 200, 255))
    text(d, (20, 575), "NIBP mmHg", "sans_bold", 30, (235, 235, 235))
    sbp, dbp = v["vitals.sbp"], v["vitals.dbp"]
    b = text(d, (20, 610), f"{sbp}/{dbp}", "sans_bold", 90, (235, 235, 235))
    text(d, (b[2] + 20, 650), f"({round((sbp + 2 * dbp) / 3)})  09:14", "sans", 36, (235, 235, 235))
    f["vitals.sbp"] = f["vitals.dbp"] = b
    text(d, (W - 20, 690), "ADULT  PACER OFF", "sans", 22, (170, 170, 170), anchor="rd")
    body.paste(scr, (130, 90))
    return body, {k: (x0 + 130, y0 + 90, x1 + 130, y1 + 90) for k, (x0, y0, x1, y1) in f.items()}


def fingertip_oximeter(spec: dict, cfg: dict, rng: random.Random):
    v = spec["values"]
    body = rounded_panel((900, 520), 200, (235, 238, 242, 255), outline=(150, 160, 175), width=4)
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle([170, 90, 735, 430], 30, fill=(8, 8, 10))
    f = {}
    text(bd, (200, 110), "%SpO2", "sans_bold", 30, (255, 210, 60))
    f["vitals.spo2"] = text(bd, (200, 150), str(v["vitals.spo2"]), "sans_bold", 180, (255, 210, 60))
    text(bd, (480, 110), "PRbpm", "sans_bold", 30, (90, 230, 120))
    f["vitals.hr"] = text(bd, (480, 185), str(v["vitals.hr"]), "sans_bold", 112, (90, 230, 120))
    text(bd, (480, 360), f"PI {spec.get('pi', 2.0)}%", "sans", 28, (170, 170, 170))
    for i in range(8):                                                  # pulse-strength bar
        bd.rectangle([700, 400 - i * 30, 716, 420 - i * 30], fill=(90, 230, 120) if i < 5 else (40, 40, 40))
    bd.ellipse([420, 450, 480, 500], fill=(200, 205, 215), outline=(150, 160, 175), width=3)     # button
    text(bd, (450, 60), "FINGERTIP PULSE OXIMETER", "sans", 24, (110, 120, 135), anchor="mm")
    return body, f


LCD = {"bg": (178, 190, 172), "on": (25, 30, 28), "off": (165, 177, 160)}


def bp_cuff(spec: dict, cfg: dict, rng: random.Random):
    v = spec["values"]
    body = rounded_panel((700, 860), 60, (245, 245, 243, 255), outline=(190, 190, 190), width=3)
    d = ImageDraw.Draw(body)
    text(d, (350, 40), "AUTOMATIC BLOOD PRESSURE MONITOR", "sans_bold", 24, (60, 80, 120), anchor="ma")
    d.rounded_rectangle([90, 100, 610, 640], 16, fill=LCD["bg"], outline=(120, 120, 120), width=3)
    f = {}
    for key, lab, unit, y, hgt in (("vitals.sbp", "SYS", "mmHg", 130, 150), ("vitals.dbp", "DIA", "mmHg", 310, 150),
                                   ("vitals.hr", "PULSE", "/min", 490, 110)):
        s = str(v[key]).rjust(3)
        f[key] = seven_segment(d, 170, y, s, hgt, LCD["on"], LCD["off"])
        text(d, (590, y + 10), lab, "sans_bold", 30, LCD["on"], anchor="ra")
        text(d, (590, y + 50), unit, "sans", 22, LCD["on"], anchor="ra")
    text(d, (115, 118), "M", "sans_bold", 24, LCD["on"])
    d.ellipse([280, 700, 420, 840], fill=(40, 90, 170))
    text(d, (350, 770), "START", "sans_bold", 26, (255, 255, 255), anchor="mm")
    return body, f


def glucometer(spec: dict, cfg: dict, rng: random.Random):
    body = rounded_panel((600, 900), 110, (40, 45, 60, 255))
    d = ImageDraw.Draw(body)
    d.rectangle([270, 0, 330, 40], fill=(230, 230, 230))                 # strip port
    d.rounded_rectangle([70, 120, 530, 560], 20, fill=LCD["bg"], outline=(20, 20, 20), width=4)
    seven_segment(d, 110, 145, "09-24", 44, LCD["on"], LCD["off"])
    seven_segment(d, 350, 145, "07:15", 44, LCD["on"], LCD["off"])
    reading = str(spec["reading"])
    f = {"vitals.glucose": seven_segment(d, 110 + 105 * (3 - len(reading)), 240, reading, 200, LCD["on"], LCD["off"])}
    text(d, (500, 470), "mg/dL", "sans_bold", 40, LCD["on"], anchor="ra")
    d.polygon([(110, 500), (170, 500), (160, 530), (100, 530)], outline=LCD["on"], width=3)   # strip icon
    for i, lab in enumerate(("M", "OK")):
        d.ellipse([140 + i * 200, 680, 260 + i * 200, 800], fill=(80, 85, 100))
        text(d, (200 + i * 200, 740), lab, "sans_bold", 34, (230, 230, 230), anchor="mm")
    text(d, (300, 620), "BLOOD GLUCOSE METER", "sans", 26, (190, 195, 210), anchor="ma")
    return body, f


def thermostat(spec: dict, cfg: dict, rng: random.Random):
    body = rounded_panel((760, 560), 40, (236, 232, 222, 255), outline=(190, 185, 170), width=3)
    d = ImageDraw.Draw(body)
    d.rounded_rectangle([80, 70, 680, 380], 14, fill=(160, 200, 220))
    text(d, (110, 90), "INSIDE", "sans_bold", 28, (20, 40, 60))
    seven_segment(d, 150, 140, spec["reading"], 190, (15, 30, 45), None)
    text(d, (420, 140), "°F", "sans_bold", 50, (15, 30, 45))
    text(d, (650, 300), f"SET {spec['setpoint']}", "sans_bold", 34, (15, 30, 45), anchor="ra")
    text(d, (650, 90), "HEAT", "sans_bold", 28, (180, 60, 20), anchor="ra")
    for i, s in enumerate(("▲", "▼", "MODE")):
        d.rounded_rectangle([110 + i * 190, 430, 250 + i * 190, 500], 12, fill=(215, 210, 198))
        text(d, (180 + i * 190, 465), s, "sans_bold", 28, (70, 70, 70), anchor="mm")
    return body, {}


def alarm_clock(spec: dict, cfg: dict, rng: random.Random):
    body = rounded_panel((900, 420), 50, (25, 25, 28, 255))
    d = ImageDraw.Draw(body)
    d.rounded_rectangle([60, 60, 840, 340], 20, fill=(12, 5, 5))
    seven_segment(d, 110, 90, spec["reading"], 220, (255, 40, 30), (40, 10, 10))
    text(d, (820, 300), "PM", "sans_bold", 30, (255, 40, 30), anchor="ra")
    text(d, (820, 80), "AL 6:30", "sans", 26, (160, 30, 25), anchor="ra")
    return body, {}


RENDERERS = {"bedside_monitor": bedside_monitor, "defib_monitor": defib_monitor,
             "fingertip_oximeter": fingertip_oximeter, "bp_cuff": bp_cuff, "glucometer": glucometer,
             "thermostat": thermostat, "alarm_clock": alarm_clock}
