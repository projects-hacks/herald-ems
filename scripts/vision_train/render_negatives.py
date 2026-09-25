"""Photos with no clinical reading: household displays with numbers (monitor-mode negatives) and non-drug
product labels (label-mode negatives). The target for each is {"facts": []}."""
from __future__ import annotations

from random import Random

from . import canvas as cv
from .render_handheld import LCD
from .spec import Panel


def household_display(rng: Random, variant: int) -> Panel:
    """Variants: 0 kitchen scale, 1 microwave/oven timer, 2 car dashboard, 3 calculator, 4 phone weather widget,
    5 (held out) bathroom scale."""
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    W, H = (900, 600) if variant != 4 else (720, 1200)
    im, d = cv.new_canvas(W, H, (0, 0, 0, 0))
    body = rng.choice([(240, 240, 240), (30, 30, 30), (200, 200, 205), (180, 60, 50)])
    cv.rounded(d, (0, 0, W, H), 40, fill=body + (255,))
    texts = []
    if variant in (0, 5):
        win = (150, 120, W - 150, 360) if variant == 0 else (250, 60, W - 250, 220)
        bg = rng.choice(LCD)
        d.rectangle(win, fill=bg)
        val = f"{rng.randint(1, 2500)}" if variant == 0 else f"{rng.uniform(95, 290):.1f}"
        h = (win[3] - win[1]) * 0.6
        cv.seven_seg(d, win[2] - 60 - cv.seven_seg_width(val, h), win[1] + 30, h, val, (20, 20, 20))
        cv.text(d, (win[2] - 10, win[3] - 40), rng.choice(["g", "oz", "lb", "kg"]), lab, 30, (20, 20, 20), anchor="ra")
        cv.text(d, (W / 2, H - 120), rng.choice(["TARE", "UNIT", "ON/OFF", "ZERO"]), lab, 34, (120, 120, 120), anchor="ma")
        texts.append(val)
    elif variant == 1:
        d.rectangle([60, 60, W * 0.6, H - 60], fill=(20, 20, 20))
        d.rectangle([W * 0.65, 80, W - 60, 220], fill=(0, 0, 0))
        val = f"{rng.randint(0, 12)}:{rng.randint(0, 59):02d}"
        cv.seven_seg(d, W * 0.67, 100, 90, val, (0, 230, 120) if rng.random() < 0.5 else (255, 60, 40))
        for i, t in enumerate(["POPCORN", "DEFROST", "POWER", "START"]):
            cv.text(d, (W * 0.67, 260 + i * 60), t, lab, 30, (60, 60, 60))
        texts.append(val)
    elif variant == 2:
        d.rectangle([0, 0, W, H], fill=(10, 10, 12))
        for cx in (W * 0.28, W * 0.72):
            d.ellipse([cx - 200, 80, cx + 200, 480], outline=(200, 200, 200), width=6)
        spd, rpm = rng.randint(0, 85), rng.uniform(0.7, 4.5)
        cv.text(d, (W * 0.28, 250), str(spd), fp, 110, (255, 255, 255), anchor="ma")
        cv.text(d, (W * 0.28, 380), "mph", lab, 34, (200, 200, 200), anchor="ma")
        cv.text(d, (W * 0.72, 250), f"{rpm:.1f}", fp, 90, (255, 255, 255), anchor="ma")
        cv.text(d, (W * 0.72, 380), "x1000 rpm", lab, 30, (200, 200, 200), anchor="ma")
        cv.text(d, (W / 2, 520), f"{rng.randint(20, 100)}°F  {rng.randint(1000, 99999)} mi", lab, 34, (255, 170, 0), anchor="ma")
        texts += [str(spd)]
    elif variant == 3:
        d.rectangle([80, 60, W - 80, 200], fill=rng.choice(LCD))
        val = str(rng.randint(10, 999999)) if rng.random() < 0.5 else f"{rng.uniform(1, 999):.2f}"
        cv.seven_seg(d, W - 120 - cv.seven_seg_width(val, 90), 85, 90, val, (20, 20, 20))
        for i in range(4):
            for j in range(4):
                cv.rounded(d, (100 + j * 180, 240 + i * 85, 240 + j * 180, 310 + i * 85), 12, fill=(60, 60, 65))
                cv.text(d, (170 + j * 180, 255 + i * 85), "789/456x123-0.=+"[i * 4 + j], lab, 36, (255, 255, 255), anchor="ma")
        texts.append(val)
    else:
        d.rectangle([20, 20, W - 20, H - 20], fill=rng.choice([(40, 110, 200), (20, 30, 60), (90, 150, 220)]))
        city = rng.choice(["San Jose", "Fremont", "Oakland", "Sacramento", "Santa Cruz"])
        t = rng.randint(30, 104)
        cv.text(d, (W / 2, 140), city, lab, 50, (255, 255, 255), anchor="ma")
        cv.text(d, (W / 2, 220), f"{t}°", fp, 200, (255, 255, 255), anchor="ma")
        cv.text(d, (W / 2, 480), f"H:{t + rng.randint(2, 12)}°  L:{t - rng.randint(5, 20)}°", lab, 44, (255, 255, 255), anchor="ma")
        for i in range(5):
            cv.text(d, (80, 620 + i * 100), f"{rng.randint(1, 12)} {rng.choice(['AM', 'PM'])}", lab, 36, (255, 255, 255))
            cv.text(d, (W - 80, 620 + i * 100), f"{t + rng.randint(-8, 8)}°", lab, 36, (255, 255, 255), anchor="ra")
        texts.append(f"{t}°")
    device = ["kitchen_scale", "microwave", "car_dashboard", "calculator", "weather_app", "bathroom_scale"][variant]
    return Panel(im, [], f"household_display/v{variant}", device, "monitor", texts=texts,
                 notes=["no patient reading on this display"])


def product_label(rng: Random, variant: int) -> Panel:
    """Non-drug labels photographed in label mode. Variants: 0 nutrition facts, 1 household cleaner,
    2 (held out) shampoo / lotion."""
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    W, H = 760, 980
    im, d = cv.new_canvas(W, H, (255, 255, 255, 255))
    ink = (15, 15, 15)
    if variant == 0:
        d.rectangle([20, 20, W - 20, H - 20], outline=ink, width=4)
        cv.text(d, (40, 40), "Nutrition Facts", fp, 64, ink)
        y = 130
        for name, val in [("Serving size", f"{rng.randint(1, 3)} cup ({rng.randint(28, 250)}g)"),
                          ("Calories", str(rng.randint(80, 450))), ("Total Fat", f"{rng.randint(0, 25)}g"),
                          ("Sodium", f"{rng.randint(0, 900)}mg"), ("Total Carbohydrate", f"{rng.randint(0, 60)}g"),
                          ("Protein", f"{rng.randint(0, 30)}g"), ("Dietary Fiber", f"{rng.randint(0, 12)}g")]:
            cv.text(d, (40, y), name, fp if name == "Calories" else lab, 34, ink)
            cv.text(d, (W - 40, y), val, fp, 34, ink, anchor="ra")
            d.line([(40, y + 50), (W - 40, y + 50)], fill=ink, width=2)
            y += 70
    else:
        col = rng.choice([(0, 120, 200), (230, 80, 0), (120, 180, 40), (180, 40, 140)])
        d.rectangle([0, 0, W, 260], fill=col)
        name = rng.choice(["FRESH CITRUS", "Ocean Breeze", "Multi-Surface", "Daily Moisture", "Lavender Calm"])
        cv.text(d, (W / 2, 80), name, fp, 64, (255, 255, 255), anchor="ma")
        kind = rng.choice(["All-Purpose Cleaner", "Glass Cleaner", "Degreaser"]) if variant == 1 else \
            rng.choice(["Shampoo", "Body Lotion", "Conditioner", "Hand Soap"])
        cv.text(d, (W / 2, 320), kind, fp, 50, ink, anchor="ma")
        cv.text(d, (W / 2, 420), f"{rng.choice([12, 16, 22, 32])} FL OZ ({rng.randint(350, 950)} mL)", lab, 36, ink, anchor="ma")
        if variant == 1:
            cv.text(d, (40, 540), "CAUTION: Keep out of reach of children.", lab, 28, ink)
            cv.text(d, (40, 590), "Do not mix with bleach.", lab, 28, ink)
    device = ["nutrition_label", "cleaner_label", "cosmetic_label"][variant]
    return Panel(im, [], f"product_label/v{variant}", device, "pill_bottle", flat=True, notes=["not a medication"])
