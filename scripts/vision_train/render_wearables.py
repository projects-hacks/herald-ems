"""Consumer screens: smartwatches (round and square), fitness bands and phone health apps. The current reading is
the one to read; resting heart rate, averages, ranges, goals, steps, calories, sleep, weather and the clock are
distractors, and a screen with only those is a negative."""
from __future__ import annotations

from random import Random

from . import canvas as cv
from .spec import Panel, Reading
from .values import glucose_display, sample, temp_display

ACCENT = [(255, 59, 48), (255, 45, 85), (52, 199, 89), (0, 122, 255), (255, 149, 0), (175, 82, 222), (0, 199, 190)]


def _clock(rng: Random) -> str:
    return f"{rng.randint(1, 12)}:{rng.randint(0, 59):02d}"


def smartwatch(rng: Random, variant: int) -> Panel:
    """Variants: 0 round heart-rate app, 1 square blood-oxygen app, 2 round watch face with complications,
    3 square multi-metric face, 4 (held out) round workout screen."""
    round_face = variant in (0, 2, 4)
    S = 600
    im, d = cv.new_canvas(S + 120, S + 420, (0, 0, 0, 0))
    strap = rng.choice([(30, 30, 30), (200, 190, 175), (60, 80, 120), (150, 40, 50), (240, 240, 240), (90, 110, 80)])
    d.rectangle([S / 2 - 150 + 60, 0, S / 2 + 150 + 60, im.height], fill=strap + (255,))
    case = rng.choice([(40, 40, 42), (200, 200, 205), (210, 180, 140), (20, 20, 22)])
    box = (40, 190, S + 80, S + 230)
    if round_face:
        d.ellipse(box, fill=case + (255,))
    else:
        cv.rounded(d, box, 110, fill=case + (255,))
    scr = (70, 220, S + 50, S + 200)
    if round_face:
        d.ellipse(scr, fill=(0, 0, 0, 255))
    else:
        cv.rounded(d, scr, 90, fill=(0, 0, 0, 255))
    x0, y0, x1, y1 = scr
    cx, cw, ch = (x0 + x1) / 2, x1 - x0, y1 - y0
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    acc = rng.choice(ACCENT)
    white = (255, 255, 255)
    grey = (150, 150, 155)
    v = sample(rng)
    readings, distract = [], []
    cv.text(d, (cx, y0 + ch * 0.1), _clock(rng), lab, 30, white, anchor="ma")
    if variant == 0:
        cv.heart(d, cx - cw * 0.22, y0 + ch * 0.3, 26, acc)
        cv.text(d, (cx - cw * 0.12, y0 + ch * 0.26), rng.choice(["Heart Rate", "HEART", "Pulse"]), lab, 28, acc)
        size = cv.fit_size(str(v.hr), fp, cw * 0.4, ch * 0.3, int(ch * 0.3))
        b = cv.text(d, (cx + cw * 0.08, y0 + ch * 0.62), str(v.hr), fp, size, white, anchor="rs")
        cv.text(d, (b[2] + 10, y0 + ch * 0.62), rng.choice(["BPM", "bpm"]), lab, 34, grey, anchor="ls")
        readings.append(Reading("vitals.hr", v.hr, b, str(v.hr)))
        extra = rng.choice([f"Resting {rng.randint(48, 72)} BPM", f"{rng.randint(45, 65)}-{rng.randint(110, 160)} today",
                            f"Avg {rng.randint(60, 90)}", f"{rng.randint(1, 9)} min ago", ""])
        if extra:
            cv.text(d, (cx, y0 + ch * 0.72), extra, lab, 28, grey, anchor="ma")
            distract.append(extra)
    elif variant == 1:
        cv.text(d, (x0 + 40, y0 + ch * 0.2), rng.choice(["Blood Oxygen", "SpO2", "Oxygen"]), lab, 34, acc)
        s = f"{v.spo2}"
        b = cv.text(d, (x0 + 40, y0 + ch * 0.35), s, fp, cv.fit_size(s, fp, cw * 0.55, ch * 0.3, int(ch * 0.3)), white)
        cv.text(d, (b[2] + 8, b[1]), "%", fp, int(ch * 0.14), white)
        readings.append(Reading("vitals.spo2", v.spo2, b, s + "%"))
        cv.text(d, (x0 + 40, y0 + ch * 0.75), rng.choice(["Just now", "Measured 9:41", "Keep still", "Last: today"]),
                lab, 26, grey)
    elif variant == 2:
        cv.text(d, (cx, y0 + ch * 0.28), _clock(rng), fp, int(ch * 0.22), white, anchor="ma")
        comps = [("steps", f"{rng.randint(200, 18000):,}"), ("weather", f"{rng.randint(28, 95)}°"),
                 ("cal", f"{rng.randint(50, 900)} cal"), ("batt", f"{rng.randint(5, 100)}%")]
        show_hr = rng.random() < 0.6
        slots = [(cx - cw * 0.22, y0 + ch * 0.62), (cx + cw * 0.22, y0 + ch * 0.62), (cx, y0 + ch * 0.78)]
        rng.shuffle(comps)
        items = ([("hr", str(v.hr))] if show_hr else []) + comps
        for (sx, sy), (kind, s) in zip(slots, items):
            if kind == "hr":
                cv.heart(d, sx - 38, sy + 16, 14, acc)
                b = cv.text(d, (sx - 18, sy), s, fp, 36, white)
                readings.append(Reading("vitals.hr", v.hr, b, s))
            else:
                cv.text(d, (sx, sy), s, lab, 32, grey, anchor="ma")
                distract.append(s)
    elif variant == 3:
        rows = [("hr", str(v.hr), "BPM"), ("spo2", str(v.spo2), "%"), ("steps", f"{rng.randint(300, 15000):,}", "steps"),
                ("cal", str(rng.randint(40, 800)), "kcal")]
        rng.shuffle(rows)
        rows = rows[:rng.randint(2, 4)]
        for i, (kind, s, unit) in enumerate(rows):
            y = y0 + ch * (0.22 + i * 0.18)
            if kind == "hr":
                cv.heart(d, x0 + 60, y + 22, 16, acc)
            b = cv.text(d, (x0 + 90, y), s, fp, 48, white)
            cv.text(d, (b[2] + 8, y + 14), unit, lab, 26, grey)
            if kind in ("hr", "spo2"):
                readings.append(Reading("vitals.hr" if kind == "hr" else "vitals.spo2", v.hr if kind == "hr" else v.spo2,
                                        b, s))
            else:
                distract.append(s)
    else:
        v2 = sample(rng, "tachy_fever")
        cv.text(d, (cx, y0 + ch * 0.2), rng.choice(["Outdoor Run", "Walk", "Cycling", "HIIT"]), lab, 28, acc, anchor="ma")
        cv.text(d, (cx, y0 + ch * 0.3), f"{rng.randint(0, 1)}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}", fp, 44,
                white, anchor="ma")
        cv.heart(d, x0 + cw * 0.28, y0 + ch * 0.52, 18, acc)
        b = cv.text(d, (x0 + cw * 0.34, y0 + ch * 0.45), str(v2.hr), fp, 70, white)
        readings.append(Reading("vitals.hr", v2.hr, b, str(v2.hr)))
        cv.text(d, (b[2] + 8, b[1] + 20), "BPM", lab, 26, grey)
        avg = f"Avg HR {rng.randint(90, 150)}"
        cv.text(d, (cx, y0 + ch * 0.68), avg, lab, 28, grey, anchor="ma")
        cv.text(d, (cx, y0 + ch * 0.78), f"{rng.uniform(0.3, 9):.2f} mi", lab, 28, grey, anchor="ma")
        distract += [avg, "distance", "elapsed time"]
    return Panel(im, readings, f"smartwatch/v{variant}", "smartwatch", "monitor", distractors=distract)


def band(rng: Random, variant: int) -> Panel:
    """Variants: 0 vertical strip heart rate, 1 vertical strip SpO2 or steps-only, 2 (held out) horizontal strip."""
    horiz = variant == 2
    W, H = (560, 200) if horiz else (200, 480)
    im, d = cv.new_canvas(W + 60, H + 400 if not horiz else H + 60, (0, 0, 0, 0))
    strap = rng.choice([(20, 20, 20), (230, 120, 150), (60, 60, 120), (50, 140, 110)])
    if horiz:
        cv.rounded(d, (0, 0, im.width, im.height), 60, fill=strap + (255,))
        scr = (30, 30, 30 + W, 30 + H)
    else:
        d.rectangle([20, 0, im.width - 20, im.height], fill=strap + (255,))
        scr = (30, 200, 30 + W, 200 + H)
    cv.rounded(d, scr, 40, fill=(0, 0, 0, 255))
    x0, y0, x1, y1 = scr
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    acc = rng.choice(ACCENT)
    v = sample(rng)
    readings, distract = [], []
    mode = "hr" if variant in (0, 2) else rng.choice(["spo2", "steps"])
    if horiz:
        cv.text(d, (x0 + 20, y0 + 20), _clock(rng), lab, 30, (200, 200, 200))
        cv.heart(d, x0 + W * 0.52, y0 + H * 0.5, 22, acc)
        b = cv.text(d, (x0 + W * 0.6, y0 + H * 0.25), str(v.hr), fp, int(H * 0.5), (255, 255, 255))
        readings.append(Reading("vitals.hr", v.hr, b, str(v.hr)))
    else:
        cv.text(d, ((x0 + x1) / 2, y0 + 20), _clock(rng), lab, 28, (200, 200, 200), anchor="ma")
        if mode == "hr":
            cv.heart(d, (x0 + x1) / 2, y0 + H * 0.3, 26, acc)
            b = cv.text(d, ((x0 + x1) / 2, y0 + H * 0.42), str(v.hr), fp, 84, (255, 255, 255), anchor="ma")
            readings.append(Reading("vitals.hr", v.hr, b, str(v.hr)))
            cv.text(d, ((x0 + x1) / 2, y0 + H * 0.68), "bpm", lab, 28, (170, 170, 170), anchor="ma")
        elif mode == "spo2":
            cv.text(d, ((x0 + x1) / 2, y0 + H * 0.28), "SpO2", lab, 30, acc, anchor="ma")
            b = cv.text(d, ((x0 + x1) / 2, y0 + H * 0.42), str(v.spo2), fp, 84, (255, 255, 255), anchor="ma")
            cv.text(d, ((x0 + x1) / 2, y0 + H * 0.68), "%", lab, 30, (170, 170, 170), anchor="ma")
            readings.append(Reading("vitals.spo2", v.spo2, b, str(v.spo2)))
        else:
            s = f"{rng.randint(100, 20000)}"
            cv.text(d, ((x0 + x1) / 2, y0 + H * 0.3), "STEPS", lab, 28, acc, anchor="ma")
            cv.text(d, ((x0 + x1) / 2, y0 + H * 0.45), s, fp, 56, (255, 255, 255), anchor="ma")
            cv.text(d, ((x0 + x1) / 2, y0 + H * 0.7), f"{rng.randint(20, 700)} kcal", lab, 26, (170, 170, 170), anchor="ma")
            distract += [s, "kcal"]
    return Panel(im, readings, f"fitness_band/v{variant}", "fitness_band", "monitor", distractors=distract)


def phone_app(rng: Random, variant: int) -> Panel:
    """Variants: 0 light summary cards, 1 dark summary cards, 2 single-metric detail page with chart,
    3 (held out) vitals list with timestamps."""
    W, H = 720, 1480
    dark = variant == 1 or (variant in (2, 3) and rng.random() < 0.4)
    bg, card = ((0, 0, 0), (28, 28, 30)) if dark else ((242, 242, 247), (255, 255, 255))
    fg, sub = ((255, 255, 255), (152, 152, 157)) if dark else ((0, 0, 0), (110, 110, 115))
    im, d = cv.new_canvas(W + 40, H + 40, (0, 0, 0, 0))
    cv.rounded(d, (0, 0, W + 40, H + 40), 70, fill=(15, 15, 18, 255))
    d.rectangle([20, 20, W + 20, H + 20], fill=bg)
    ox, oy = 20, 20
    fp, lab = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    v = sample(rng)
    fahr, mmol = rng.random() < 0.6, rng.random() < 0.2
    cv.text(d, (ox + 40, oy + 20), _clock(rng), fp, 30, fg)
    cv.battery(d, ox + W - 90, oy + 26, 44, 20, rng.random(), fg)
    title = rng.choice(["Summary", "Health", "Today", "Vitals", "Browse", "Health Connect"])
    cv.text(d, (ox + 40, oy + 90), title, fp, 64, fg)
    t_shown, t_c = temp_display(rng, v.temp_c, fahr)
    g_shown, g_mgdl = glucose_display(rng, v.glucose, mmol)
    metrics = {
        "hr": ("Heart Rate", str(v.hr), "BPM", "vitals.hr", v.hr),
        "spo2": ("Blood Oxygen", str(v.spo2), "%", "vitals.spo2", v.spo2),
        "bp": ("Blood Pressure", f"{v.sbp}/{v.dbp}", "mmHg", None, (v.sbp, v.dbp)),
        "temp": ("Body Temperature", t_shown, "°F" if fahr else "°C", "vitals.temp", t_c),
        "glucose": ("Blood Glucose", g_shown, "mmol/L" if mmol else "mg/dL", "vitals.glucose", g_mgdl),
    }
    fillers = [("Steps", f"{rng.randint(200, 16000):,}", "steps"), ("Resting Heart Rate", str(rng.randint(48, 75)), "BPM"),
               ("Sleep", f"{rng.randint(4, 9)} hr {rng.randint(0, 59)} min", ""),
               ("Respiratory Rate", f"{rng.randint(12, 18)}", "breaths/min (sleep avg)"),
               ("Active Energy", str(rng.randint(80, 900)), "kcal"), ("Walking Heart Rate Average", str(rng.randint(80, 115)), "BPM"),
               ("Weight", f"{rng.randint(110, 260)}", "lb")]
    readings, distract = [], []

    def put_value(x, y, size, key, shown, unit, value, name):
        if key is None:
            sbp, dbp = value
            b1 = cv.text(d, (x, y), str(sbp), fp, size, fg)
            b2 = cv.text(d, (b1[2], y), "/", fp, size, fg)
            b3 = cv.text(d, (b2[2], y), str(dbp), fp, size, fg)
            cv.text(d, (b3[2] + 10, b3[3] - 34), unit, lab, 28, sub)
            return [Reading("vitals.sbp", sbp, b1, str(sbp)), Reading("vitals.dbp", dbp, b3, str(dbp))]
        b = cv.text(d, (x, y), shown, fp, size, fg)
        cv.text(d, (b[2] + 10, b[3] - 34), unit, lab, 28, sub)
        return [Reading(key, value, b, shown + " " + unit)]

    if variant in (0, 1):
        names = rng.sample(list(metrics), rng.randint(1, 4))
        cards = [("m", n) for n in names] + [("f", f) for f in rng.sample(fillers, rng.randint(1, 3))]
        rng.shuffle(cards)
        y = oy + 200
        for kind, item in cards[:6]:
            ch = 190
            cv.rounded(d, (ox + 30, y, ox + W - 30, y + ch), 26, fill=card)
            if kind == "m":
                name, shown, unit, key, value = metrics[item]
                cv.text(d, (ox + 60, y + 22), name, fp, 30, rng.choice([(255, 59, 48), (0, 122, 255), (175, 82, 222)]))
                cv.text(d, (ox + W - 60, y + 26), rng.choice(["9:41 AM", "Now", "2 min ago", "Today 7:12"]), lab, 24, sub,
                        anchor="ra")
                cv.text(d, (ox + 60, y + 66), rng.choice(["Latest", "Most recent", ""]), lab, 24, sub)
                readings += put_value(ox + 60, y + 96, 64, key, shown, unit, value, name)
            else:
                name, shown, unit = item
                cv.text(d, (ox + 60, y + 22), name, fp, 30, (255, 149, 0))
                b = cv.text(d, (ox + 60, y + 96), shown, fp, 64, fg)
                cv.text(d, (b[2] + 10, b[3] - 34), unit, lab, 28, sub)
                distract.append(f"{name} {shown}")
            y += ch + 24
    elif variant == 2:
        name_key = rng.choice(list(metrics))
        name, shown, unit, key, value = metrics[name_key]
        cv.text(d, (ox + 40, oy + 190), name, fp, 44, fg)
        cv.text(d, (ox + 40, oy + 260), rng.choice(["LATEST", "Latest reading", "Most recent · today"]), lab, 28, sub)
        readings += put_value(ox + 40, oy + 300, 110, key, shown, unit, value, name)
        cv.trend(d, rng, (ox + 40, oy + 520, ox + W - 40, oy + 900), rng.choice([(255, 59, 48), (0, 122, 255)]),
                 n=rng.randint(7, 30), bars_style=rng.random() < 0.5)
        rng_txt = rng.choice([f"RANGE {rng.randint(50, 70)}–{rng.randint(110, 150)}", f"AVERAGE {rng.randint(60, 100)}",
                              f"Min {rng.randint(40, 60)}  Max {rng.randint(120, 170)}", f"Daily avg {rng.randint(60, 99)}"])
        cv.text(d, (ox + 40, oy + 940), rng_txt, fp, 34, sub)
        distract.append(rng_txt)
        for i in range(rng.randint(2, 4)):
            cv.text(d, (ox + 40, oy + 1030 + i * 70), rng.choice(["Yesterday", "Mon", "Tue", "Sep 3", "Last week"]), lab,
                    30, sub)
            cv.text(d, (ox + W - 40, oy + 1030 + i * 70), rng.choice(["72", "118/76", "96%", "98.1", "104"]), lab, 30, sub,
                    anchor="ra")
        distract.append("history rows")
    else:
        names = rng.sample(list(metrics), rng.randint(2, 5))
        y = oy + 200
        cv.rounded(d, (ox + 30, y, ox + W - 30, y + 140 * len(names) + 40), 26, fill=card)
        for n in names:
            name, shown, unit, key, value = metrics[n]
            cv.text(d, (ox + 60, y + 30), name, lab, 30, fg)
            cv.text(d, (ox + 60, y + 72), rng.choice(["Today, 8:05", "Just now", "10 min ago", "Today, 11:47"]), lab, 24, sub)
            readings += put_value(ox + W * 0.5, y + 34, 56, key, shown, unit, value, name)
            d.line([(ox + 60, y + 136), (ox + W - 60, y + 136)], fill=sub, width=1)
            y += 140
    return Panel(im, readings, f"phone_app/v{variant}", "phone_app", "monitor", distractors=distract)
