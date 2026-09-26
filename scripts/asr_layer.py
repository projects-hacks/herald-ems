#!/usr/bin/env python3
"""The measured ASR layer for run F (MODEL_PLAN §0k "Measured ASR noise"): real Whisper transcripts of training lines
spoken by TTS voices in synthetic ambulance-cabin noise, kept as training inputs only where the labels still hold.

  python scripts/asr_layer.py plan --out <work>/plan.jsonl                 # stratified sample, voice, rate, noise
  ~/.venvs/piper/bin/python scripts/asr_tts.py --plan <work>/plan.jsonl --voices ~/.cache/piper-voices --out <work>/wav
  python scripts/asr_layer.py transcribe --plan <work>/plan.jsonl --wav <work>/wav   # -> data/annotated/asr_f.jsonl
  python scripts/asr_layer.py judge                                          # kept/dropped + reasons, measured rates

`transcribe` runs the production speech path (herald/models/stt.py WhisperSTT: the same weights, priming prompt,
settings and echo stripping). `judge` keeps a transcript only when every label the clean line grounded is still
grounded by the transcript under the production rules (herald/extraction/grounding.py), and every number label
still has its number; misheard drug names are kept (reading through them is the point). The builder adds the kept
rows to train with `--asr` (scripts/build_train_set.py). Training-data preparation only.

The speech is Piper TTS, not people: the rates measured here are TTS-speech rates, a floor on real field error."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from herald.config import load_text, load_yaml  # noqa: E402
from herald.core.vocabulary import default_vocabulary  # noqa: E402
from herald.extraction.grounding import default_grounding  # noqa: E402

OUT = ROOT / "data" / "annotated" / "asr_f.jsonl"
REPORT = ROOT / "data" / "annotated" / "asr_f_report.json"
DRUG_KEYS = {"meds.list": None, "meds.anticoagulant": None, "meds.given": "drug"}


def cfg() -> dict:
    return load_yaml("training.yaml")["asr_noise"]


def facts(row: dict) -> list:
    return json.loads(row["completion"])["f"]


def speakable(text: str) -> str:
    """What the TTS voice is given: the line as written, with a digit/digit pair ("182/104") read as "over", the way
    a medic says a pressure (espeak would otherwise say "slash")."""
    return re.sub(r"(\d)\s*/\s*(\d)", r"\1 over \2", text)


# ---------------------------------------------------------------- plan
def plan(a) -> None:
    c = cfg()
    rng = random.Random(c["seed"])
    rows = [json.loads(l) for l in open(a.train)]
    rng.shuffle(rows)
    by_key: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        for k in {f[0] for f in facts(r)}:
            by_key[k].append(i)
    keys = default_vocabulary().keys
    picked: list[int] = []
    seen: set[int] = set()
    for k in sorted(keys, key=lambda k: len(by_key.get(k, []))):          # rarest keys first
        have = sum(1 for i in by_key.get(k, []) if i in seen)
        for i in by_key.get(k, []):
            if have >= c["min_rows_per_key"]:
                break
            if i not in seen:
                seen.add(i)
                picked.append(i)
                have += 1
    for i in range(len(rows)):
        if len(picked) >= c["sample_rows"]:
            break
        if i not in seen:
            seen.add(i)
            picked.append(i)
    conds = list(c["conditions"])
    shares = [conds[j % len(conds)] for j in range(len(picked))]
    rng.shuffle(shares)
    out = []
    for j, (i, cond) in enumerate(zip(picked, shares)):
        r = rows[i]
        out.append({"clip": f"{j:04d}", "source_id": r["id"], "source": r["source"], "said": speakable(r["raw_text"]),
                    "raw_text": r["raw_text"], "completion": r["completion"], "voice": rng.choice(c["voices"]),
                    "length_scale": round(rng.uniform(*c["length_scale"]), 3), "condition": cond,
                    "snr_db": c["conditions"][cond]})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    cover = Counter(k for i in picked for k in {f[0] for f in facts(rows[i])})
    print(json.dumps({"planned": len(out), "keys_covered": f"{len(cover)}/{len(keys)}",
                      "fewest": sorted(cover.items(), key=lambda x: x[1])[:8], "conditions": Counter(shares)}))


def paired(a) -> None:
    """The first `n` planned lines, each spoken by the same voice at every noise condition: a paired plan, so the
    per-condition rates compare the same sentences (the main plan gives each line one condition)."""
    c = cfg()
    items = [json.loads(l) for l in open(a.plan)][:a.n]
    out = [{**it, "clip": it["clip"], "condition": cond, "snr_db": snr}
           for it in items for cond, snr in c["conditions"].items()]
    Path(a.out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    print(json.dumps({"paired_clips": len(out), "lines": len(items)}))


# ---------------------------------------------------------------- transcribe
def transcribe(a) -> None:
    import numpy as np
    import soundfile as sf
    from herald.config.settings import Settings
    from herald.models.stt import WhisperSTT
    from scripts.cabin_noise import SR, mix

    c = cfg()
    items = [json.loads(l) for l in open(a.plan)]
    stt = WhisperSTT(Settings.from_env().stt_model)
    clips = []
    for n, it in enumerate(items):
        audio, sr = sf.read(Path(a.wav) / f"{it['clip']}.wav", dtype="float32")
        speech = WhisperSTT._mono16k(audio, sr)
        mixed, parts = mix(speech, it["snr_db"], np.random.default_rng([c["seed"], n]), c, SR)
        it["noise"] = parts
        it["seconds"] = round(len(mixed) / SR, 2)
        clips.append(mixed)
    order = sorted(range(len(items)), key=lambda i: len(clips[i]))       # similar lengths batch together
    partial = Path(a.plan).with_name("transcripts_partial.jsonl")        # resumable: a crash keeps what is done
    texts: dict[int, dict] = {}
    if partial.exists():
        texts = {d["i"]: d for d in map(json.loads, open(partial))}
    todo = [i for i in order if i not in texts]
    with open(partial, "a") as log:
        for s in range(0, len(todo), a.chunk):
            idx = todo[s:s + a.chunk]
            res = stt.transcribe_many([clips[i] for i in idx], SR, batch_size=a.batch)
            for i, r in zip(idx, res):          # the production gates apply here too; a dropped clip keeps its reason
                texts[i] = {"i": i, "text": r["text"], "dropped": r.get("dropped"), "language": r.get("language")}
                log.write(json.dumps(texts[i], ensure_ascii=False) + "\n")
            log.flush()
            print(f"transcribed {len(texts)}/{len(order)}", flush=True)
    for i, it in enumerate(items):
        it["whisper"] = texts[i]["text"]
        it["stt_dropped"], it["language"] = texts[i].get("dropped"), texts[i].get("language")
    Path(a.out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items))
    print(json.dumps({"transcribed": len(items), "out": str(a.out)}))


# ---------------------------------------------------------------- judge + measure
def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[.'][a-z0-9]+)*", text.lower())


def align(ref: list[str], hyp: list[str]) -> tuple[int, list[tuple[int | None, int | None]]]:
    """Levenshtein distance and the alignment as (ref index, hyp index) pairs (None = insertion/deletion)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    pairs, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    return d[n][m], pairs[::-1]


def heard_as(said: str, heard: str, name: str) -> str | None:
    """What Whisper wrote where `name` was said: the transcript words aligned to the name's words."""
    rt, ht = tokens(said), tokens(heard)
    nt = tokens(name)
    start = next((i for i in range(len(rt) - len(nt) + 1) if rt[i:i + len(nt)] == nt), None)
    if start is None or not nt:
        return None
    _, pairs = align(rt, ht)
    end = start + len(nt)
    before = [j for i, j in pairs if i is not None and i < start and j is not None]
    after = [j for i, j in pairs if i is not None and i >= end and j is not None]
    lo, hi = (before[-1] + 1 if before else 0), (after[0] if after else len(ht))
    return " ".join(ht[lo:hi])         # every transcript word between the words said around the name


def drugs_said(row_facts: list, said: str) -> list[str]:
    low = said.lower()
    out = []
    for k, v, *_ in row_facts:
        if k not in DRUG_KEYS:
            continue
        field = DRUG_KEYS[k]
        vals = [v.get(field)] if field and isinstance(v, dict) else v if isinstance(v, list) else [v]
        for x in vals:
            if isinstance(x, str) and len(x) >= 4 and x.lower() != "none" and re.search(rf"\b{re.escape(x.lower())}\b", low):
                out.append(x)
    return sorted(set(out))


def numbers_in(text: str, g) -> list[set[float]]:
    """Each number said in `text`: a digit token's value, or every reading of a run of number words."""
    out = [{float(m.group())} for m in re.finditer(r"\d+(?:\.\d+)?", text)]
    out += [vals for _, vals in g.spoken.spans(text) if vals]
    return out


def numeric_labels(row_facts: list):
    for k, v, *_ in row_facts:
        items = v.items() if isinstance(v, dict) else [(None, v)]
        for f, x in items:
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                yield (f"{k}.{f}" if f else k), float(x)


def labels_lost(row_facts: list, said: str, heard: str, g) -> str | None:
    """Why the transcript no longer supports the line's labels, or None: a label the said line grounds that the
    transcript does not (production grounding rules), or a number label whose number was said but not heard."""
    for k, v, *_ in row_facts:
        if g.supported(k, v, said) and not g.supported(k, v, heard):
            return f"grounding lost: {k}"
    heard_nums, said_nums = g.numbers_said(heard), g.numbers_said(said)
    for name, x in numeric_labels(row_facts):
        if any(abs(x - s) < 0.05 for s in said_nums) and not any(abs(x - h) < 0.05 for h in heard_nums):
            return f"number lost: {'.'.join(name.split('.')[:2])}"
    return None


def verdict(it: dict, row_facts: list, g, c: dict, prompt: str, wer: float) -> tuple[bool, str]:
    heard, raw = it["whisper"].strip(), it["raw_text"]
    if it.get("stt_dropped"):
        return False, f"speech gate: {it['stt_dropped']}"
    if not heard:
        return False, "empty transcript"
    pw = tokens(prompt)
    prompt_runs = {tuple(pw[i:i + 5]) for i in range(len(pw) - 4)}
    ht, rt = tokens(heard), tokens(raw)
    said_runs = {tuple(rt[i:i + 5]) for i in range(len(rt) - 4)}
    if any(tuple(ht[i:i + 5]) in prompt_runs - said_runs for i in range(len(ht) - 4)):
        return False, "prompt echo"
    grams = Counter(tuple(ht[i:i + 4]) for i in range(len(ht) - 3))
    said_grams = Counter(tuple(rt[i:i + 4]) for i in range(len(rt) - 3))
    if len(ht) > c["max_length_ratio"] * max(1, len(tokens(it["said"]))) or \
            any(n >= 3 and n > said_grams.get(gram, 0) for gram, n in grams.items()):
        return False, "hallucination (repeats or too long)"
    art = re.compile(c["tts_artifacts"], re.I)
    if art.search(heard) and not art.search(it["said"]):
        return False, "TTS artifact (IV read as a Roman numeral)"
    lost = labels_lost(row_facts, raw, heard, g)
    if lost:
        return False, lost
    if wer > c["max_wer"]:
        return False, f"unintelligible (WER > {c['max_wer']})"
    return True, "kept"


def judge(a) -> None:
    from transformers import WhisperTokenizer
    from herald.models.weights import local_weights

    c = cfg()
    g = default_grounding()
    prompt = load_text("prompts/stt_prompt.txt")
    norm = WhisperTokenizer.from_pretrained(local_weights("openai/whisper-large-v3-turbo")).normalize
    train = {json.loads(l)["id"]: json.loads(l) for l in open(a.train)}
    items = [json.loads(l) for l in open(a.asr)]
    wer_acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    num_acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    drug_acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    misheard: Counter = Counter()
    reasons: Counter = Counter()
    reasons_by_cond: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        cond = it["condition"]
        if "completion" not in it:          # the labels the line had when it was sampled, kept with the record
            it["completion"] = train[it["source_id"]]["completion"]
        row_facts = facts(it)
        if a.measure_only:
            it["kept"], it["reason"] = True, "kept"
        ref, hyp = norm(it["said"]).split(), norm(it["whisper"]).split()
        dist, _ = align(ref, hyp)
        it["wer"] = round(dist / max(1, len(ref)), 4)
        for key in (cond, "all"):
            wer_acc[key][0] += dist
            wer_acc[key][1] += len(ref)
        heard_nums = g.numbers_said(re.sub(r"(?<=\d),(?=\d{3})", "", it["whisper"]))   # "2,105" is 2105
        for vals in numbers_in(it["said"], g):
            ok = any(abs(v - h) < 0.05 for v in vals for h in heard_nums)
            for key in (cond, "all"):
                num_acc[key][0] += not ok
                num_acc[key][1] += 1
        for d in drugs_said(row_facts, it["said"]):
            got = heard_as(it["said"], it["whisper"], d)
            ok = got is not None and got.replace(" ", "") == d.lower().replace(" ", "")
            if not ok:
                misheard[f"{d.lower()} -> {got or '(dropped)'}"] += 1
            for key in (cond, "all"):
                drug_acc[key][0] += not ok
                drug_acc[key][1] += 1
        if not a.measure_only:
            it["kept"], it["reason"] = verdict(it, row_facts, g, c, prompt, it["wer"])
        reasons[it["reason"]] += 1
        reasons_by_cond[cond][it["reason"].split(":")[0]] += 1
    if not a.measure_only:
        Path(a.asr).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items))
    rate = lambda acc: {k: {"rate": round(e / n, 4) if n else None, "errors": e, "n": n} for k, (e, n) in acc.items()}
    report = {"speech": "Piper TTS voices (not human speech), synthetic cabin noise, production Whisper path",
              "clips": len(items), "kept": sum(it["kept"] for it in items),
              "wer": rate(wer_acc), "number_error": rate(num_acc), "drug_error": rate(drug_acc),
              "drug_misrecognitions_top20": misheard.most_common(20),
              "reasons": dict(reasons.most_common()), "reasons_by_condition": {k: dict(v) for k, v in reasons_by_cond.items()}}
    Path(a.report).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--train", default=str(ROOT / "data" / "train_f" / "train.jsonl"))
    p.add_argument("--out", required=True)
    t = sub.add_parser("transcribe")
    t.add_argument("--plan", required=True)
    t.add_argument("--wav", required=True)
    t.add_argument("--out", default=str(OUT))
    t.add_argument("--batch", type=int, default=16)
    t.add_argument("--chunk", type=int, default=128)
    q = sub.add_parser("paired")
    q.add_argument("--plan", required=True)
    q.add_argument("--n", type=int, default=200)
    q.add_argument("--out", required=True)
    j = sub.add_parser("judge")
    j.add_argument("--measure-only", action="store_true", help="rates only; no verdicts written (paired runs)")
    j.add_argument("--asr", default=str(OUT))
    j.add_argument("--train", default=str(ROOT / "data" / "train_f" / "train.jsonl"),
                   help="where the sampled lines' labels are looked up when a record does not carry them")
    j.add_argument("--report", default=str(REPORT))
    a = ap.parse_args()
    {"plan": plan, "paired": paired, "transcribe": transcribe, "judge": judge}[a.cmd](a)


if __name__ == "__main__":
    main()
