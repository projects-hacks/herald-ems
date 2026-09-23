#!/usr/bin/env python3
"""Synthetic training data for the extractor fine-tune (P10.0), by reverse generation.

1. Code samples a FACT BUNDLE (the label) following docs/LABELING_GUIDE.md.
2. The local teacher model writes N different utterances that state exactly those facts.
3. Each utterance is VALIDATED: every label value must be findable in the text (digits, spoken
   numbers, drug brand/generic, relation word), and the rules extractor must not find keys that
   aren't in the bundle (the teacher added facts). Rejects are counted, never silently kept.
4. ~50% get ASR-style noise (lowercase, dropped punctuation, fillers) that doesn't change meaning.
5. Split train/dev/test by TEMPLATE (call type + key set + phenomena), never randomly.

The label is always the bundle, never the teacher's output.

  python scripts/gen_synth.py --bundles 400 --per-bundle 5 --out data/synth --concurrency 16
"""
import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from herald.extract_rules import ANTICOAG, extract as rules_extract  # noqa: E402

URL = "http://127.0.0.1:8080/v1/chat/completions"
BRANDS = {"warfarin": ["warfarin", "Coumadin"], "apixaban": ["Eliquis", "apixaban"],
          "rivaroxaban": ["Xarelto", "rivaroxaban"], "dabigatran": ["Pradaxa"], "enoxaparin": ["Lovenox"]}
OTHER_MEDS = ["metformin", "lisinopril", "atorvastatin", "metoprolol", "insulin", "albuterol", "levothyroxine"]
ALLERGENS = ["penicillin", "sulfa", "aspirin", "codeine", "latex", "morphine", "iodine"]
RELATIONS = ["husband", "wife", "daughter", "son", "mother", "father", "caregiver", "brother", "sister"]
HOSPITALS = ["Valley Medical", "Regional", "O'Connor", "Good Samaritan", "Stanford", "Kaiser San Jose"]
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def spoken(n: int) -> list[str]:
    """Plausible spoken forms of an integer 0-399: '142' -> ['one forty two', 'one hundred forty two', ...]."""
    def two(x):
        return ONES[x] if x < 20 else TENS[x // 10] + ("" if x % 10 == 0 else " " + ONES[x % 10])
    forms = [str(n)]
    if n < 100:
        forms.append(two(n))
    else:
        h, r = divmod(n, 100)
        forms += [f"{ONES[h]} hundred" + (f" {two(r)}" if r else ""),
                  f"{ONES[h]} {two(r) if r >= 10 else ('oh ' + ONES[r] if r else 'hundred')}"]
    return forms


def sample_bundle(rng: random.Random) -> dict:
    call = rng.choice(["stroke"] * 3 + ["chest_pain"] * 2 + ["fall", "respiratory", "diabetic", "sepsis"])
    facts, ph, rel = [], set(), None
    who = "medic"
    if rng.random() < 0.35:
        who = rng.choice(["family", "family", "patient", "bystander"])
        rel = rng.choice(RELATIONS) if who == "family" else ("neighbor" if who == "bystander" else None)
        ph.add("attribution")

    def add(k, v, role="medic"):
        facts.append([k, v, role])
    if rng.random() < 0.6:
        add("patient.age", rng.randint(19, 94)); ph.add("demographics")
        if rng.random() < 0.8:
            add("patient.sex", rng.choice(["F", "M"]))
    vitals = rng.sample(["hr", "bp", "spo2", "rr", "glucose", "temp"], k=rng.randint(0, 3))
    for v in vitals:
        if v == "hr": add("vitals.hr", rng.randint(38, 150))
        if v == "bp":
            s = rng.randint(80, 210); add("vitals.sbp", s); add("vitals.dbp", rng.randint(45, min(120, s - 20)))
        if v == "spo2": add("vitals.spo2", rng.randint(84, 100))
        if v == "rr": add("vitals.rr", rng.randint(8, 34))
        if v == "glucose": add("vitals.glucose", rng.randint(38, 420))
        if v == "temp": add("vitals.temp", round(rng.uniform(35.2, 40.1), 1)); ph.add("temp")
    if vitals and rng.random() < 0.3:
        ph.add("correction")
    if rng.random() < 0.4:
        ph.add("spoken_numbers")
    hist_role = who if who != "medic" else "medic"
    if call == "stroke" and rng.random() < 0.6:
        add("stroke.lkw", rng.choice(["1:40", "10 pm", "9 am", "3:15", "7:30", "noon"]), hist_role)
    if rng.random() < 0.4:
        g = rng.choice(list(BRANDS))
        add("meds.anticoagulant", g, hist_role); add("meds.list", [g], hist_role); ph.add("brand_names")
    elif rng.random() < 0.15:
        add("meds.anticoagulant", "none", hist_role); ph.add("negation")
    if rng.random() < 0.3:
        if rng.random() < 0.4:
            add("allergies", [], hist_role); ph.add("negation")
        else:
            add("allergies", [rng.choice(ALLERGENS)], hist_role)
    if rng.random() < 0.15:
        add("transport.eta_min", rng.randint(3, 25))
        if rng.random() < 0.6:
            add("transport.destination", rng.choice(HOSPITALS))
    if rng.random() < 0.2:
        add("vitals.on_oxygen", rng.random() < 0.5)
    if rng.random() < 0.2:
        add("vitals.consciousness", rng.choice(["A", "C", "V", "P", "U"]))
    if rng.random() < 0.08:
        facts = []; ph = {"no_facts"}
    keyset = ",".join(sorted({f[0] for f in facts}))
    template = hashlib.sha1(f"{call}|{keyset}|{','.join(sorted(ph))}".encode()).hexdigest()[:10]
    return {"call": call, "facts": facts, "phenomena": sorted(ph), "relation": rel, "template": template}


def describe(b: dict) -> str:
    lines = []
    for k, v, r in b["facts"]:
        src = "" if r == "medic" else f" (reported by the {b['relation'] or r})"
        lines.append(f"- {k} = {json.dumps(v)}{src}")
    return "\n".join(lines) or "- (no clinical facts: a logistics or radio line)"


def teacher_prompt(b: dict, n: int) -> str:
    style = []
    if "spoken_numbers" in b["phenomena"]: style.append("say at least one number in words (e.g. 'one forty two')")
    if "correction" in b["phenomena"]: style.append("misspeak one vital value, then correct it ('correction' or 'I mean'); the final value must be the one listed")
    if "brand_names" in b["phenomena"]: style.append("you may use a brand name for the anticoagulant (Coumadin, Eliquis, Xarelto, Pradaxa, Lovenox)")
    if "temp" in b["phenomena"]: style.append("say temperature in Fahrenheit in some versions (convert exactly: C*9/5+32, one decimal)")
    return (f"You are writing training data. Write {n} DIFFERENT ways a US paramedic on a {b['call'].replace('_', ' ')} call "
            f"would say ALL of these facts in ONE short spoken utterance (5-40 words), and NO other clinical facts:\n{describe(b)}\n"
            "Rules: state each fact exactly (same numbers). Facts marked '(reported by X)' MUST be introduced with 'X says/states/reports'; "
            "facts WITHOUT that mark must NOT be attributed to anyone (the medic observed them). Never start with a speaker label like 'Husband:'. "
            "Say a temperature only once, in Celsius or Fahrenheit, not both. Do not describe oxygen, consciousness or alertness unless listed. "
            "vary style: EMS shorthand (sats, pt, yo, A&O, NKDA), terse or conversational. "
            + ("Style: " + "; ".join(style) + ". " if style else "")
            + 'Return JSON: {"u": ["...", "..."]}')


def findable(k, v, text: str, relation) -> bool:
    t = text.lower()
    if v is None:
        return True
    if k == "vitals.on_oxygen":
        return bool(re.search(r"room air", t)) if v is False else bool(
            re.search(r"oxygen|nasal cannula|\bnc\b|non.?rebreather|\bnrb\b|liters?|\blpm\b|\bo2 (at|via|by)", t))
    if k == "stroke.onset_witnessed":
        return bool(re.search(r"witness|saw|in front of|watched", t)) if v else bool(re.search(r"found|unwitnessed|woke", t))
    if isinstance(v, bool):
        return True
    if isinstance(v, list):
        return all(findable(k, x, text, relation) for x in v) if v else bool(
            re.search(r"nkda|no known|no allergies|denies", t))
    if k == "vitals.temp":
        f = round(v * 9 / 5 + 32, 1)
        return any(s in t for s in (str(v), str(f), str(int(f)) if f.is_integer() else str(f)))
    if isinstance(v, (int, float)):
        return any(s in t for s in spoken(int(v)))
    s = str(v).lower()
    if k in ("meds.anticoagulant",) and s == "none":
        return bool(re.search(r"no (blood thinner|anticoag)|denies|not on", t))
    if s in BRANDS:
        return any(b.lower() in t for b in BRANDS[s])
    if k == "patient.sex":
        return bool(re.search(r"female|woman|lady|yof|\bf\b" if s == "f" else r"\bmale|\bman\b|gentleman|yom|\bm\b", t))
    if k == "vitals.consciousness":
        pat = {"a": r"\balert|a ?& ?o|oriented", "c": r"confus|disorient", "v": r"to voice|to verbal|verbal stimul",
               "p": r"to pain|painful stimul", "u": r"unresponsive"}[s]
        return bool(re.search(pat, t))
    return s.replace(":", "").replace(" ", "") in t.replace(":", "").replace(" ", "")


def valid(b: dict, u: str) -> tuple[bool, str]:
    for k, v, r in b["facts"]:
        if not findable(k, v, u, b["relation"]):
            return False, f"missing {k}={v}"
    attributed = any(r != "medic" for _, _, r in b["facts"])
    if re.match(r"^\s*\w+\s*:", u):
        return False, "speaker-label prefix"
    if attributed and b["relation"] and b["relation"] not in u.lower():
        return False, "attribution missing"
    if not attributed and re.search(r"\b(says|said|states|stated|reports|reported|per (the |her |his )?\w+|according to)\b|"
                                    + "|".join(RELATIONS), u.lower()):
        return False, "unwanted attribution"
    extra = {f.key for f in rules_extract(u)} - {k for k, _, _ in b["facts"]} - {"complaint.chief", "stroke.deficits"}
    if extra:
        return False, f"teacher added {sorted(extra)}"
    return True, ""


def asr_noise(u: str, rng: random.Random) -> str:
    x = u.lower()
    x = re.sub(r"(?<!\d)[.,;!?]|[.,;!?](?!\d)", "" if rng.random() < 0.5 else " ", x)   # keep 39.3 and 1:40
    if rng.random() < 0.5:
        words = x.split(); i = rng.randrange(len(words) + 1)
        words.insert(i, rng.choice(["uh", "um", "so", "like"])); x = " ".join(words)
    return re.sub(r"\s+", " ", x).strip()


def completion(b: dict) -> str:
    rows = []
    for k, v, r in b["facts"]:
        who = {"medic": "m", "patient": "p", "bystander": "b"}.get(r) or f"f:{b['relation']}"
        rows.append([k, v, who])
    return json.dumps({"f": rows}, separators=(",", ":"))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=int, default=400)
    ap.add_argument("--per-bundle", type=int, default=5)
    ap.add_argument("--out", default="data/synth")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--model", default="omni")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    bundles = [sample_bundle(rng) for _ in range(a.bundles)]
    sem = asyncio.Semaphore(a.concurrency)
    stats = {"generated": 0, "kept": 0, "rejected": {}, "errors": 0}
    rows = []
    t0 = time.time()
    async with httpx.AsyncClient(timeout=120) as c:
        async def one(b):
            async with sem:
                body = {"model": a.model, "temperature": 0.9, "max_tokens": 700,
                        "messages": [{"role": "user", "content": teacher_prompt(b, a.per_bundle)}],
                        "response_format": {"type": "json_object"},
                        "chat_template_kwargs": {"enable_thinking": False}}
                try:
                    r = await c.post(URL, json=body)
                    us = json.loads(re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S).group(0))["u"]
                except Exception:
                    stats["errors"] += 1
                    return
                for u in us[: a.per_bundle]:
                    stats["generated"] += 1
                    ok, why = valid(b, u)
                    if not ok:
                        key = why.split(" ")[0] + " " + (why.split(" ")[1] if " " in why else "")
                        stats["rejected"][key] = stats["rejected"].get(key, 0) + 1
                        continue
                    noisy = rng.random() < 0.5
                    rows.append({"template": b["template"], "call": b["call"], "phenomena": b["phenomena"] + (["asr_noise"] if noisy else []),
                                 "text": asr_noise(u, rng) if noisy else u, "facts": b["facts"], "relation": b["relation"],
                                 "completion": completion(b)})
                    stats["kept"] += 1
        await asyncio.gather(*(one(b) for b in bundles))
    templates = sorted({r["template"] for r in rows})
    rng.shuffle(templates)
    n = len(templates)
    split = {t: ("test" if i < 0.1 * n else "dev" if i < 0.2 * n else "train") for i, t in enumerate(templates)}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for part in ("train", "dev", "test"):
        with open(out / f"{part}.jsonl", "w") as fh:
            for r in rows:
                if split[r["template"]] == part:
                    fh.write(json.dumps(r) + "\n")
    stats.update({"seconds": round(time.time() - t0), "templates": n,
                  "split_rows": {p: sum(1 for r in rows if split[r["template"]] == p) for p in ("train", "dev", "test")}})
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
