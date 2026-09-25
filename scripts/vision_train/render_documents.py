"""Documents: resuscitation order forms (several generic POLST/MOLST/prehospital DNR layouts, invented wording
and headers, no state seal), and documents that carry no resuscitation order: medical ID cards and bracelets,
discharge summaries, intake questionnaires with unrelated checkboxes, insurance cards."""
from __future__ import annotations

from random import Random

from . import canvas as cv
from .render_labels import TEXT, person
from .spec import Panel, Reading

CPR_WORDS = [("Attempt Resuscitation/CPR", "Do Not Attempt Resuscitation/DNR"),
             ("YES CPR: Attempt Resuscitation", "NO CPR: Do Not Attempt Resuscitation"),
             ("Full resuscitation (CPR)", "Do not resuscitate (DNR / allow natural death)"),
             ("CPR - attempt to resuscitate", "DNR - do not attempt to resuscitate")]
TITLES = ["PHYSICIAN ORDERS FOR LIFE-SUSTAINING TREATMENT", "MEDICAL ORDERS FOR SCOPE OF TREATMENT",
          "PORTABLE MEDICAL ORDERS", "CLINICIAN ORDERS FOR LIFE-SUSTAINING TREATMENT",
          "TRANSPORTABLE PHYSICIAN ORDERS FOR PATIENT PREFERENCES"]


def _mark(d, rng: Random, box, ink, style: str) -> None:
    x0, y0, x1, y1 = box
    w = max(3, int((x1 - x0) / 7))
    if style == "x":
        d.line([(x0 + 3, y0 + 3), (x1 - 3, y1 - 3)], fill=ink, width=w)
        d.line([(x0 + 3, y1 - 3), (x1 - 3, y0 + 3)], fill=ink, width=w)
    elif style == "check":
        d.line([(x0 + 2, (y0 + y1) / 2), ((x0 + x1) / 2, y1 - 2), (x1 + 8, y0 - 10)], fill=ink, width=w)
    else:
        d.rectangle([x0 + 4, y0 + 4, x1 - 4, y1 - 4], fill=ink)


def order_form(rng: Random, variant: int) -> Panel:
    """Variants: 0 lettered sections stacked, 1 horizontal CPR choice, 2 single-box prehospital DNR order,
    3 (held out) circle-the-choice table."""
    W, H = 1100, 1420
    paper = rng.choice([(255, 255, 255), (252, 240, 250), (255, 250, 225), (240, 250, 240)])
    im, d = cv.new_canvas(W, H, paper + (255,))
    f_head, f_reg = cv.pick_font(rng, "bold"), cv.pick_font(rng, rng.choice(["sans", "serif"]))
    f_hand = cv.pick_font(rng, "hand")
    ink, pen = (20, 20, 20), rng.choice([(20, 40, 150), (10, 10, 10), (30, 30, 90)])
    cpr, dnr = rng.choice(CPR_WORDS)
    choice = rng.choices(["cpr", "dnr", "none_b_only", "both", "none"], weights=[0.36, 0.44, 0.08, 0.04, 0.08])[0]
    style = rng.choice(["x", "x", "check", "fill"])
    title = rng.choice(TITLES) if variant != 2 else rng.choice(["PREHOSPITAL DO NOT RESUSCITATE ORDER",
                                                                "OUT-OF-HOSPITAL DNR ORDER", "EMS DNR ORDER FORM"])
    size = cv.fit_size(title, f_head, W - 80, 60, 44)
    cv.text(d, (W / 2, 40), title, f_head, size, ink, anchor="ma")
    cv.text(d, (40, 120), f"Patient: {person(rng)}    DOB: {rng.randint(1, 12)}/{rng.randint(1, 28)}/19{rng.randint(20, 90)}",
            f_reg, 26, ink)
    d.line([(40, 165), (W - 40, 165)], fill=ink, width=3)
    readings, notes = [], []
    y = 190
    if variant == 2:
        if choice in ("cpr", "both"):
            choice = "dnr"
        body = ("I, the undersigned physician, order that no cardiopulmonary resuscitation be attempted "
                "for the patient named above if cardiac or respiratory arrest occurs.")
        for i in range(0, len(body), 70):
            cv.text(d, (40, y), body[i:i + 70], f_reg, 26, ink)
            y += 38
        y += 30
        bx = (60, y, 110, y + 50)
        d.rectangle(bx, outline=ink, width=4)
        tb = cv.text(d, (130, y + 4), "DO NOT RESUSCITATE (DNR)", f_head, 38, ink)
        if choice == "dnr":
            _mark(d, rng, bx, pen, style)
            readings.append(Reading("code_status", "DNR", cv.union(bx, tb), "DNR"))
        else:
            notes.append("order box left blank")
        y += 120
    else:
        cv.text(d, (40, y), rng.choice(["A", "Section A", "1."]) + "  " +
                rng.choice(["CARDIOPULMONARY RESUSCITATION (CPR)", "RESUSCITATION", "CPR ORDER"]), f_head, 30, ink)
        y += 44
        cv.text(d, (60, y), "If the patient has no pulse and is not breathing:", f_reg, 24, ink)
        y += 50
        opts = [("cpr", cpr), ("dnr", dnr)]
        if rng.random() < 0.5:
            opts.reverse()
        boxes = {}
        for i, (k, label) in enumerate(opts):
            if variant == 1:
                bx0 = 60 + i * (W - 100) / 2
                bx = (bx0, y, bx0 + 44, y + 44)
                tb = cv.text(d, (bx0 + 60, y + 4), label if len(label) < 30 else label[:30], f_reg, 26, ink)
                boxes[k] = (bx, tb)
            elif variant == 3:
                tb = cv.text(d, (100, y + i * 80), label, f_head, 30, ink)
                boxes[k] = (tb, tb)
            else:
                bx = (60, y + i * 70, 104, y + i * 70 + 44)
                tb = cv.text(d, (124, y + i * 70 + 4), label, f_reg, 28, ink)
                boxes[k] = (bx, tb)
            if variant != 3:
                d.rectangle(boxes[k][0], outline=ink, width=3)
        y += 170
        chosen = {"cpr": ["cpr"], "dnr": ["dnr"], "both": ["cpr", "dnr"]}.get(choice, [])
        for k in chosen:
            bx, tb = boxes[k]
            if variant == 3:
                d.ellipse([tb[0] - 20, tb[1] - 16, tb[2] + 20, tb[3] + 16], outline=pen, width=5)
            else:
                _mark(d, rng, bx, pen, style)
        if choice in ("cpr", "dnr"):
            bx, tb = boxes[choice]
            readings.append(Reading("code_status", "full code" if choice == "cpr" else "DNR", cv.union(bx, tb),
                                    cpr if choice == "cpr" else dnr))
        elif choice == "both":
            notes.append("both resuscitation options marked: not clearly checked")
        else:
            notes.append("resuscitation section left blank")
        cv.text(d, (40, y), rng.choice(["B", "Section B", "2."]) + "  " +
                rng.choice(["MEDICAL INTERVENTIONS", "INITIAL TREATMENT ORDERS", "LEVEL OF TREATMENT"]), f_head, 30, ink)
        y += 50
        b_opts = ["Full Treatment", "Selective Treatment", "Comfort-Focused Treatment"]
        b_pick = rng.randrange(3) if (choice != "none" or rng.random() < 0.3) else None
        for i, lab in enumerate(b_opts):
            bx = (60, y, 100, y + 40)
            d.rectangle(bx, outline=ink, width=3)
            cv.text(d, (120, y + 4), lab, f_reg, 26, ink)
            if b_pick == i or (choice == "none_b_only" and i == 1):
                _mark(d, rng, bx, pen, style)
            y += 60
        y += 20
        cv.text(d, (40, y), rng.choice(["C", "Section C", "3."]) + "  ARTIFICIALLY ADMINISTERED NUTRITION", f_head, 28, ink)
        y += 50
        for lab in ["Long-term nutrition by tube", "Trial period", "No artificial nutrition"]:
            d.rectangle((60, y, 100, y + 40), outline=ink, width=3)
            cv.text(d, (120, y + 4), lab, f_reg, 26, ink)
            y += 58
    y += 30
    cv.text(d, (40, y), "Signature of clinician", f_reg, 22, ink)
    cv.text(d, (60, y + 30), person(rng), f_hand, 44, pen)
    d.line([(40, y + 90), (W / 2, y + 90)], fill=ink, width=2)
    cv.text(d, (W / 2 + 40, y + 40), f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/{rng.choice([2024, 2025, 2026])}",
            f_hand, 40, pen)
    return Panel(im, readings, f"order_form/v{variant}", "polst" if variant != 2 else "dnr_order", "form",
                 texts=[title, cpr, dnr], flat=True, notes=notes)


def non_order_document(rng: Random, variant: int) -> Panel:
    """Documents without a resuscitation order (form-mode negatives). Variants: 0 medical ID wallet card,
    1 medical ID bracelet, 2 discharge summary page, 3 intake questionnaire with checked boxes,
    4 (held out) insurance card."""
    f_head, f_reg = cv.pick_font(rng, "bold"), cv.pick_font(rng, "sans")
    ink = (20, 20, 20)
    readings: list[Reading] = []
    conds = rng.sample(TEXT["conditions"], rng.randint(1, 3))
    allergy = rng.choice(TEXT["allergens"])
    if variant == 1:
        W, H = 1100, 300
        im, d = cv.new_canvas(W, H, (0, 0, 0, 0))
        cv.rounded(d, (0, 40, W, H - 40), 110, fill=rng.choice([(200, 200, 205), (210, 180, 120), (60, 60, 65)]) + (255,))
        cv.heart(d, 140, H / 2, 50, (200, 30, 40))
        cv.text(d, (230, 80), conds[0], f_head, 44, (30, 30, 30))
        ab = cv.text(d, (230, 140), f"ALLERGIC TO {allergy}", f_head, 40, (30, 30, 30))
        readings.append(Reading("allergies", allergy.lower(), ab, allergy))
        return Panel(im, readings, f"non_order_document/v{variant}", "medical_id_bracelet", "form",
                     texts=[conds[0], allergy])
    W, H = {0: (1000, 630), 2: (1100, 1420), 3: (1100, 1420), 4: (1000, 630)}[variant]
    im, d = cv.new_canvas(W, H, (255, 255, 255, 255))
    if variant in (0, 4):
        band = rng.choice([(200, 30, 40), (20, 90, 170), (30, 130, 80)])
        d.rounded_rectangle([0, 0, W, H], 40, fill=(250, 250, 250))
        d.rectangle([0, 0, W, 110], fill=band)
        title = "MEDICAL ALERT" if variant == 0 else rng.choice(["HEALTH PLAN", "Member ID Card", "INSURANCE"])
        cv.text(d, (30, 30), title, f_head, 48, (255, 255, 255))
        cv.text(d, (30, 140), f"Name: {person(rng)}", f_reg, 34, ink)
        if variant == 0:
            cv.text(d, (30, 200), "Conditions: " + ", ".join(conds), f_reg, 28, ink)
            ab = cv.text(d, (30, 260), f"Allergies: {allergy}", f_reg, 28, ink)
            readings.append(Reading("allergies", allergy.lower(), ab, allergy))
            cv.text(d, (30, 320), f"Emergency contact: {person(rng)} ({rng.randint(200, 989)}) {rng.randint(200, 999)}-"
                    f"{rng.randint(1000, 9999)}", f_reg, 26, ink)
        else:
            cv.text(d, (30, 200), f"Member ID: {rng.randint(10**8, 10**9)}", f_reg, 30, ink)
            cv.text(d, (30, 260), f"Group: {rng.randint(1000, 99999)}   PCP copay ${rng.choice([10, 20, 30])}", f_reg, 28, ink)
        return Panel(im, readings, f"non_order_document/v{variant}", "medical_id_card" if variant == 0 else "insurance_card",
                     "form", texts=conds + [allergy], flat=True)
    if variant == 2:
        cv.text(d, (40, 40), rng.choice(["DISCHARGE SUMMARY", "Discharge Instructions", "HOSPITAL DISCHARGE"]), f_head, 44, ink)
        y = 120
        for line in [f"Patient: {person(rng)}", f"Admitted: {rng.randint(1, 12)}/{rng.randint(1, 28)}  Discharged: "
                     f"{rng.randint(1, 12)}/{rng.randint(1, 28)}", "Diagnosis: " + conds[0].title(),
                     "Follow up with your primary care provider in 1 week.", "Return if chest pain, shortness of breath,",
                     "fever over 101 F, or new weakness.", "Diet: as tolerated. Activity: as tolerated."]:
            cv.text(d, (40, y), line, f_reg, 30, ink)
            y += 52
        return Panel(im, readings, f"non_order_document/v{variant}", "discharge_summary", "form", texts=conds, flat=True)
    cv.text(d, (40, 40), rng.choice(["PATIENT INTAKE QUESTIONNAIRE", "New Patient Form", "Health History"]), f_head, 44, ink)
    y = 130
    for q in rng.sample(["Do you smoke?", "Any recent travel?", "Do you exercise weekly?", "Consent to text reminders",
                         "Wear glasses or contacts?", "Prefer a female provider?", "OK to leave voicemail?",
                         "Have you had a flu shot this year?", "Photography consent"], 6):
        cv.text(d, (40, y), q, f_reg, 30, ink)
        for j, opt in enumerate(["Yes", "No"]):
            bx = (700 + j * 160, y, 740 + j * 160, y + 40)
            d.rectangle(bx, outline=ink, width=3)
            cv.text(d, (bx[2] + 12, y + 4), opt, f_reg, 26, ink)
            if rng.random() < 0.5 and (j == 0) == (rng.random() < 0.5):
                _mark(d, rng, bx, (20, 40, 150), rng.choice(["x", "check"]))
        y += 80
    return Panel(im, readings, f"non_order_document/v{variant}", "intake_form", "form", flat=True)
