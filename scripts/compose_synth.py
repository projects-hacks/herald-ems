#!/usr/bin/env python3
"""Template composition of training data for the extractor fine-tune (P10.0).

Why templates: the local teacher model (Nemotron-Omni, reasoning off) produced mislabeled or
unnatural utterances (only 7/194 passed strict validation in the 2026-09-23 pilot). Composing
utterances from phrase banks makes every label correct by construction and follows
docs/LABELING_GUIDE.md exactly (clause-scoped attribution, corrections, negations, spoken numbers).
Generalization is judged on the independently written gold v1 set, not on this data.

  python scripts/compose_synth.py --n 3000 --out data/synth --seed 7
Output rows: {"template", "text", "by", "speaker", "facts", "completion", "phenomena"}; split by template.
"""
import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_synth import BRANDS, spoken  # noqa: E402

REL = ["husband", "wife", "daughter", "son", "mother", "father", "caregiver", "brother", "sister", "girlfriend"]
BYST = ["neighbor", "bystander", "coworker", "passerby"]
ALLERGENS = ["penicillin", "sulfa", "aspirin", "codeine", "latex", "morphine", "iodine", "shellfish"]
OTHER_MEDS = ["metformin", "lisinopril", "atorvastatin", "metoprolol", "levothyroxine", "amlodipine"]
DEST = ["Valley Medical", "Regional", "O'Connor", "Good Samaritan", "Stanford", "Kaiser San Jose", "El Camino"]
LOGISTICS = ["Medic 12 en route", "copy that", "we're loading now", "stand by one", "switching to channel two",
             "we're on scene", "requesting a lift assist", "clear the driveway please", "updating the chart"]


def num(rng, n, spoken_p):
    return rng.choice(spoken(n)[1:]) if rng.random() < spoken_p and n >= 20 else str(n)


def pron(sex):
    return {"F": "she", "M": "he"}.get(sex, rng_choice_global(["she", "he"]))


_R = random.Random(0)


def rng_choice_global(xs):
    return _R.choice(xs)


def compose(rng: random.Random):
    call = rng.choice(["stroke"] * 3 + ["chest pain"] * 2 + ["fall", "shortness of breath", "diabetic", "sepsis"])
    facts, clauses, ph = [], [], set()
    by, speaker = "medic", None
    sp = 0.35 if rng.random() < 0.4 else 0.0
    if sp:
        ph.add("spoken_numbers")
    if rng.random() < 0.08:                                     # no facts at all
        return {"text": rng.choice(LOGISTICS), "facts": [], "phenomena": ["no_facts"], "by": by, "speaker": None,
                "call": "logistics"}
    sex = rng.choice(["F", "M", None])
    if rng.random() < 0.65:
        age = rng.randint(19, 95)
        sw = {"F": ["female", "woman", "F", "yof"], "M": ["male", "man", "M", "yom"]}
        if sex is None:
            clauses.append(rng.choice([f"{num(rng, age, sp)} year old", f"{age} yo", f"age {age}"]))
        else:
            w = rng.choice(sw[sex])
            if w in ("yof", "yom"):
                clauses.append(f"{age} {w}")
                ph.add("shorthand")
            else:
                clauses.append(rng.choice([f"{num(rng, age, sp)}-year-old {w}", f"{age} yo {w}", f"{age} year old {w}"]))
            facts.append(["patient.sex", sex, "medic"])
        facts.append(["patient.age", age, "medic"])
    # vitals, observed by the medic
    corrected = False
    for v in rng.sample(["hr", "bp", "spo2", "rr", "glucose", "temp", "o2", "loc"], k=rng.randint(0, 4)):
        if v == "hr":
            n = rng.randint(38, 160); lab = rng.choice(["pulse", "HR", "heart rate", "heart rate's", "pulse is"])
            if not corrected and rng.random() < 0.15:
                wrong = n + rng.choice([-10, 10, 20]); clauses.append(f"{lab} {num(rng, wrong, sp)}, {rng.choice(['correction', 'I mean', 'sorry'])}, {num(rng, n, sp)}")
                corrected = True; ph.add("correction")
            else:
                clauses.append(f"{lab} {num(rng, n, sp)}")
            facts.append(["vitals.hr", n, "medic"])
        if v == "bp":
            s = rng.randint(78, 220); d = rng.randint(40, min(125, s - 20))
            lab = rng.choice(["BP", "pressure", "blood pressure", "pressure's"])
            if not corrected and rng.random() < 0.12:
                ws = s + rng.choice([-10, 10]); clauses.append(f"{lab} {ws} over {d}, {rng.choice(['correction', 'I mean'])}, {s} over {d}")
                corrected = True; ph.add("correction")
            else:
                sep = rng.choice([" over ", "/"]) if not sp else " over "
                clauses.append(f"{lab} {num(rng, s, sp)}{sep}{num(rng, d, sp)}")
            facts += [["vitals.sbp", s, "medic"], ["vitals.dbp", d, "medic"]]
        if v == "spo2":
            n = rng.randint(82, 100)
            clauses.append(rng.choice([f"sats {num(rng, n, sp)}", f"satting {num(rng, n, sp)}", f"SpO2 {n}", f"O2 sat {n} percent", f"sat {n}"]))
            facts.append(["vitals.spo2", n, "medic"]); ph.add("shorthand")
        if v == "rr":
            n = rng.randint(8, 36)
            clauses.append(rng.choice([f"resps {n}", f"breathing {num(rng, n, sp)}", f"respiratory rate {n}", f"RR {n}", f"respirations {n}"]))
            facts.append(["vitals.rr", n, "medic"])
        if v == "glucose":
            n = rng.randint(35, 450)
            if not corrected and rng.random() < 0.15:
                w = n + rng.choice([-10, 10, 100]); clauses.append(f"sugar {w}, correction, {n}"); corrected = True; ph.add("correction")
            else:
                clauses.append(rng.choice([f"sugar {num(rng, n, sp)}", f"glucose {num(rng, n, sp)}", f"BGL {n}", f"D-stick {n}", f"blood sugar is {num(rng, n, sp)}"]))
            facts.append(["vitals.glucose", n, "medic"])
        if v == "temp":
            c = round(rng.uniform(35.0, 40.5), 1)
            if rng.random() < 0.4:
                f = round(c * 9 / 5 + 32, 1); c = round((f - 32) * 5 / 9, 1)
                clauses.append(rng.choice([f"temp {f} Fahrenheit", f"temp is {f} F", f"{f} degrees Fahrenheit"])); ph.add("fahrenheit")
            else:
                clauses.append(rng.choice([f"temp {c}", f"temperature {c} C", f"temp {c} Celsius"]))
            facts.append(["vitals.temp", c, "medic"])
        if v == "o2":
            if rng.random() < 0.5:
                clauses.append(rng.choice(["on room air", "room air"])); facts.append(["vitals.on_oxygen", False, "medic"])
            else:
                clauses.append(rng.choice([f"on {rng.randint(2, 6)} liters nasal cannula", "on a non-rebreather", "on 15 liters NRB", "we put her on oxygen"]))
                facts.append(["vitals.on_oxygen", True, "medic"])
        if v == "loc":
            lvl, phr = rng.choice([("A", "alert and oriented"), ("A", "A&O x4"), ("A", "alert"), ("C", "confused"),
                                   ("C", "new confusion"), ("V", "responds to voice"), ("P", "responds to pain only"),
                                   ("U", "unresponsive")])
            clauses.append(phr); facts.append(["vitals.consciousness", lvl, "medic"])
    # history: either the medic says it, or someone else's clause
    hist = []
    if call == "stroke" and rng.random() < 0.6:
        hist.append(("lkw", rng.choice(["1:40", "10 pm", "9 am", "3:15", "7:30", "11 am", "2:05"])))
    if rng.random() < 0.4:
        hist.append(("anticoag", rng.choice(list(BRANDS))))
    elif rng.random() < 0.12:
        hist.append(("anticoag_none", None))
    if rng.random() < 0.3:
        hist.append(("allergy", rng.choice([None] * 2 + ALLERGENS)))
    source = rng.choice(["medic", "medic", "family", "patient", "bystander"]) if hist else "medic"
    rel = rng.choice(REL) if source == "family" else rng.choice(BYST) if source == "bystander" else None
    p = {"F": "she", "M": "he"}.get(sex) or rng.choice(["she", "he"])
    parts = []
    for kind, val in hist:
        if kind == "lkw":
            parts.append(rng.choice([f"{p} was fine at {val}", f"{p} was normal at {val}", f"last known well {val}"]))
            facts.append(["stroke.lkw", val, source])
        if kind == "anticoag":
            brand = rng.choice(BRANDS[val]); ph.add("brand_names") if brand != val else None
            parts.append(rng.choice([f"{p} takes {brand}", f"{p}'s on {brand}", f"on {brand}"]))
            facts += [["meds.anticoagulant", val, source], ["meds.list", [val], source]]
        if kind == "anticoag_none":
            parts.append(rng.choice(["no blood thinners", f"{p} denies blood thinners", "not on any anticoagulants"]))
            facts.append(["meds.anticoagulant", "none", source]); ph.add("negation")
        if kind == "allergy":
            if val is None:
                parts.append(rng.choice(["no known allergies", "NKDA", "no allergies"])); facts.append(["allergies", [], source]); ph.add("negation")
            else:
                parts.append(rng.choice([f"allergic to {val}", f"{p}'s allergic to {val}"])); facts.append(["allergies", [val], source])
    if parts:
        if source == "medic":
            clauses += parts
        else:
            who = rel if rel else "patient"
            verb = rng.choice(["says", "states", "reports", "tells me"])
            clauses.append(f"{'the ' if who in BYST else ''}{who} {verb} " + " and ".join(parts))
            ph.add("attribution")
    if rng.random() < 0.15:
        eta = rng.randint(3, 25); dest = rng.choice(DEST)
        clauses.append(rng.choice([f"ETA {eta} minutes to {dest}", f"transporting to {dest}, ETA {eta}", f"{eta} minutes out"]))
        facts.append(["transport.eta_min", eta, "medic"])
        if dest in clauses[-1]:
            facts.append(["transport.destination", dest, "medic"])
    if not clauses:
        return compose(rng)
    rng.shuffle(clauses)
    joiner = rng.choice([", ", ". ", ", ", " "])
    text = joiner.join(clauses)
    if rng.random() < 0.2:
        ws = text.split(); ws.insert(rng.randrange(len(ws) + 1), rng.choice(["uh", "um", "so"])); text = " ".join(ws); ph.add("disfluency")
    noise = rng.random()
    if noise < 0.10:      # punctuation lost entirely (rare with Whisper, which punctuates)
        text = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", "", text.lower()); ph.add("asr_noise")
    elif noise < 0.40:    # lowercase only, punctuation kept
        text = text.lower(); ph.add("asr_noise")
    elif rng.random() < 0.7:
        text = text[0].upper() + text[1:] + "."
    if len(facts) >= 4:
        ph.add("multi_event")
    # other speaker into the mic: occasionally hand the mic to the family member for their clause only
    return {"text": text, "facts": facts, "phenomena": sorted(ph), "by": "medic", "speaker": None, "call": call,
            "relation": rel}


def completion(row):
    out = []
    for k, v, r in row["facts"]:
        who = {"medic": "m", "patient": "p", "bystander": "b"}.get(r) or f"f:{row['relation']}"
        out.append([k, v, who])
    return json.dumps({"f": out}, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--out", default="data/synth")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    rows = []
    for _ in range(a.n):
        r = compose(rng)
        keyset = ",".join(sorted({f[0] for f in r["facts"]}))
        r["template"] = hashlib.sha1(f"{r['call']}|{keyset}|{','.join(r['phenomena'])}".encode()).hexdigest()[:10]
        r["completion"] = completion(r)
        rows.append(r)
    temps = sorted({r["template"] for r in rows}); rng.shuffle(temps)
    n = len(temps)
    split = {t: ("test" if i < 0.1 * n else "dev" if i < 0.2 * n else "train") for i, t in enumerate(temps)}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for part in ("train", "dev", "test"):
        with open(out / f"{part}.jsonl", "w") as fh:
            for r in rows:
                if split[r["template"]] == part:
                    fh.write(json.dumps(r) + "\n")
    print(json.dumps({"rows": len(rows), "templates": n,
                      "split": {p: sum(1 for r in rows if split[r["template"]] == p) for p in ("train", "dev", "test")}}))


if __name__ == "__main__":
    main()
