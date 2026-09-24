"""Scene objects a medic might photograph in the patient's home: a weekly pill organizer and a home oxygen
cylinder with a nasal cannula. Same contract as displays.py."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from .primitives import text

DAYS = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")


def pill_organizer(spec: dict, cfg: dict, rng: random.Random):
    W, H = 1400, 520
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    full = set(spec.get("full_days", []))
    pills = [(240, 240, 240), (250, 200, 60), (230, 120, 140), (120, 180, 230)]
    for i, day in enumerate(DAYS):
        x = 20 + i * 195
        d.rounded_rectangle([x, 40, x + 180, 480], 22, fill=(120, 170, 220, 235), outline=(70, 110, 160), width=4)
        d.rounded_rectangle([x + 10, 50, x + 170, 130], 14, fill=(90, 140, 200, 255))
        text(d, (x + 90, 90), day, "sans_bold", 44, (255, 255, 255), anchor="mm")
        if day in full:
            for j in range(5):
                cx, cy = x + 50 + (j % 2) * 75 + rng.uniform(-8, 8), 190 + j * 55 + rng.uniform(-6, 6)
                col = pills[j % len(pills)]
                d.ellipse([cx - 28, cy - 18, cx + 28, cy + 18], fill=col, outline=(90, 90, 90), width=2)
    return img, {}


def oxygen_cylinder(spec: dict, cfg: dict, rng: random.Random):
    W, H = 900, 1300
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([250, 300, 550, 1280], 120, fill=(40, 140, 70, 255), outline=(20, 80, 40), width=5)
    d.rectangle([290, 330, 320, 1240], fill=(90, 190, 120, 255))                   # highlight
    d.rectangle([355, 180, 445, 310], fill=(170, 170, 175, 255))                   # valve
    d.ellipse([300, 60, 500, 260], fill=(230, 230, 230), outline=(80, 80, 80), width=6)   # gauge
    for k in range(9):
        a = 3.6 + k * 0.28
        d.line([(400 + 80 * math.cos(a), 160 + 80 * math.sin(a)), (400 + 95 * math.cos(a), 160 + 95 * math.sin(a))],
               fill=(40, 40, 40), width=4)
    d.line([(400, 160), (460, 110)], fill=(200, 30, 30), width=6)
    d.rectangle([290, 620, 510, 820], fill=(250, 250, 250, 255), outline=(20, 80, 40), width=3)
    text(d, (400, 650), "OXYGEN", "sans_bold", 50, (20, 110, 50), anchor="ma")
    text(d, (400, 720), "U.S.P.", "sans_bold", 36, (20, 110, 50), anchor="ma")
    text(d, (400, 770), "NON-FLAMMABLE GAS 2", "sans", 18, (20, 110, 50), anchor="ma")
    tube = [(445, 240), (560, 260), (700, 380), (760, 560), (720, 760), (640, 900), (700, 1040), (820, 1080)]
    d.line(tube, fill=(200, 230, 240), width=14, joint="curve")
    d.ellipse([760, 1040, 880, 1120], outline=(200, 230, 240), width=12)            # cannula loop
    return img, {}


RENDERERS = {"pill_organizer": pill_organizer, "oxygen_cylinder": oxygen_cylinder}
