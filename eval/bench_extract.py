#!/usr/bin/env python3
"""Extraction benchmark: same gold set, same scoring, any extractor.

  python eval/bench_extract.py --extractor rules
  python eval/bench_extract.py --extractor llm --model omni          # a model served by ZRT on :8080
  python eval/bench_extract.py --extractor llm --model omni --gold eval/gold_v0.jsonl --out eval/results.jsonl

  python eval/bench_extract.py --rescore dump.jsonl --gold eval/gold_v1.jsonl  # re-score saved predictions

Scores atomic facts: precision / recall / F1, role accuracy on matched facts, JSON validity, and
per-utterance latency. Numbers go straight into the deck.

What an atomic fact is (scorer v2, 2026-09-23; v1 scored whole facts):
- scalar keys: (key, normalized value);
- list keys (meds.list, allergies): one atom per item, so a 2-of-3 med list earns 2 true positives and
  1 miss instead of a miss plus a false positive; list facts for the same key are unioned, as the patient
  state does for accumulating keys; an empty list (e.g. "no known allergies") is the atom (key, "<none>");
- time keys: compared after normalizing how a time is said ("since 3 a.m." == "3 am", "fifteen minutes
  ago" == "15 minutes ago", "06:30" == "0630");
- free-text keys (FREE_TEXT): presence only, reported separately.
Drug names are NOT normalized by the scorer: mapping brands and misspellings to generic names is the
extractor's job (LABELING_GUIDE §4).
"""
import argparse
import json
import yaml
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herald.config import Settings  # noqa: E402
from herald.core.schema import CapturedBy, Role, source_role  # noqa: E402
from herald.core.vocabulary import default_vocabulary  # noqa: E402
from herald.extraction import ModelExtractor  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.baselines.rules_extractor import RulesExtractor  # noqa: E402  (baseline rows only)
from eval.baselines.rules_plus_model import ExtractionPipeline  # noqa: E402  (baseline rows only)
from herald.models import LocalLLMClient  # noqa: E402

KEYS = default_vocabulary().keys


TIME_KEYS = {"stroke.lkw", "symptom.onset", "ecg.twelve_lead_time"}
_NUM = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_NUM.update({"twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "half": "30"})
_TIME_FILLER = r"\b(since|for|at|around|about|approximately|approx|roughly|like|the)\b"


def norm_time(v) -> str:
    """How a time was said, reduced to its content: "since 3 a.m." -> "3am", "an hour ago" -> "1hourago"."""
    import re
    s = str(v).strip().lower().replace("a.m.", "am").replace("p.m.", "pm").replace("o'clock", "")
    s = re.sub(r"\ban?\s+(hour|minute|day|week)", r"1 \1", s)
    s = re.sub(r"\b(twenty|thirty|forty|fifty)[\s-](one|two|three|four|five|six|seven|eight|nine)\b",
               lambda m: str(int(_NUM[m.group(1)]) + int(_NUM[m.group(2)])), s)
    s = re.sub(r"[a-z]+", lambda m: _NUM.get(m.group(0), m.group(0)), s)
    s = re.sub(r"\bthe past\b", "", s)            # "for the past 2 hours" == "2 hours"
    s = re.sub(_TIME_FILLER, "", s)
    s = re.sub(r"[\s:.,~-]", "", s)
    return s.lstrip("0") or "0"


def norm(key, v):
    if key in TIME_KEYS:
        return norm_time(v)
    if isinstance(v, list):
        return tuple(sorted(str(x).strip().lower() for x in v))
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 1)
    s = str(v).strip().lower().replace(".", "").replace(" ", "")
    try:
        return round(float(s), 1)
    except ValueError:
        return s


# Free-text keys can't be scored by exact string match (paraphrase is not an error). They are scored
# separately by key presence; the headline F1 covers structured keys only.
FREE_TEXT = {"complaint.chief", "stroke.deficits", "transport.destination", "scene.notes", "trauma.mechanism",
             "trauma.injuries"}
# Scored separately against their own gold files (eval/scoring.yaml; --group-gold, --gfast-gold), so the headline
# F1 stays comparable with every number published before these keys existed.
SEPARATE_PREFIX = "exam.gfast."
GROUPS = yaml.safe_load(open(Path(__file__).resolve().parent / "scoring.yaml"))["groups"]


def group_of(key: str) -> str | None:
    for name, g in GROUPS.items():
        if key in g.get("keys", []) or any(key.startswith(p) for p in g.get("prefixes", [])):
            return name
    return None


def atoms(facts) -> dict:
    """(key, normalized value) -> role, for facts given as (key, value, role). See the module docstring."""
    out = {}
    for k, v, r in facts:
        if KEYS.get(k, {}).get("type") == "record" and isinstance(v, dict):
            try:
                v = default_vocabulary().coerce(k, v)       # the same field normalization as the app ("husband" -> family)
            except ValueError:
                pass
            # one atom per stated field of the event, tied to its identity ("aspirin"): partial credit per field
            ident = " ".join(str(v.get(KEYS[k]["identity"], "")).strip().lower().split())
            for f, x in v.items():
                if x not in (None, ""):
                    out[(k, ident, f, norm_time(x) if f == "time" else norm(k, x))] = r
        elif KEYS.get(k, {}).get("type") == "list":
            items = v if isinstance(v, list) else [v]
            if not items:
                out[(k, "<none>")] = r
            for x in items:
                out[(k, " ".join(str(x).strip().lower().split()))] = r
        else:
            out[(k, norm(k, v))] = r
    return out


def score(gold, pred, free_text=False):
    """gold, pred: lists of (key, value, role). Returns tp, fp, fn, role_ok, extra, missed."""
    if free_text:
        keep = lambda k: k in FREE_TEXT
    else:
        keep = lambda k: k not in FREE_TEXT and group_of(k) is None
    # gold rows may carry a 4th element (the source's relation, LABELING_GUIDE §3); scoring uses key, value, role
    gold = [(f[0], f[1], f[2]) for f in gold if keep(f[0])]
    pred = [(f[0], f[1], f[2]) for f in pred if keep(f[0])]
    if free_text:   # presence only
        g = {(k, None): r for k, v, r in gold}
        p = {(k, None): r for k, v, r in pred}
        tp = set(g) & set(p)
        return len(tp), len(p) - len(tp), len(g) - len(tp), sum(1 for x in tp if g[x] == p[x]), [], []
    g, p = atoms(gold), atoms(pred)
    tp = set(g) & set(p)
    role_ok = sum(1 for x in tp if g[x] == p[x])
    return len(tp), len(p) - len(tp), len(g) - len(tp), role_ok, sorted(set(p) - set(g)), sorted(set(g) - set(p))


def group_atoms(facts) -> dict:
    """Atoms for a key group: free-text keys by presence (paraphrase is not an error), the rest exactly."""
    out = atoms([f for f in facts if f[0] not in FREE_TEXT])
    out.update({(k, "<present>"): r for k, v, r in facts if k in FREE_TEXT})
    return out


def build_extractor(kind: str, model: str | None):
    """The same extractors the app wires (herald/api/context.py), for one served model label."""
    s = Settings.from_env()
    client = LocalLLMClient(s.llm_url, model or s.llm_model)
    rules = RulesExtractor()
    model_x = ModelExtractor(client, finetuned_labels=s.finetuned_models)
    ext = {"rules": rules, "llm": model_x,
           "pipeline": ExtractionPipeline(rules, model_x, model_available=client.available)}[kind]
    return ext, model_x, client


def predict(a, rows):
    """Run the extractor on every row. Yields (row, pred as (key, value, role) tuples, ms, tokens, error)."""
    ext, model_x, _ = build_extractor(a.extractor, a.model)
    for r in rows:
        by = CapturedBy(r.get("by", "medic"))
        role = source_role(by, r.get("speaker"))              # as the app does (herald/api/capture.py)
        model_x.last_usage = {}
        t0 = time.perf_counter()
        err = None
        try:
            ctx = {"dispatch": r.get("dispatch")} if isinstance(ext, ModelExtractor) else {}   # run E sees it
            pred = ext.extract(r["text"], by, role, r.get("speaker"), **ctx)
        except Exception as e:
            pred, err = [], f"{type(e).__name__}: {str(e)[:200]}"
        ms = (time.perf_counter() - t0) * 1000
        tokens = (model_x.last_usage or {}).get("completion_tokens") if a.extractor != "rules" else None
        yield r, [(f.key, f.value, f.role.value) for f in pred], ms, tokens, err


def replay(path, rows):
    """Saved predictions from a --dump file, in gold order."""
    saved = {d["id"]: d for d in map(json.loads, open(path))}
    for r in rows:
        d = saved[r["id"]]
        yield r, [tuple(x) for x in d["pred"]], d["ms"], d.get("tokens"), d.get("error")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["rules", "llm", "pipeline"], default="rules")
    ap.add_argument("--model", default=None, help="served model name (ZRT label)")
    ap.add_argument("--gold", default="eval/gold_v0.jsonl")
    ap.add_argument("--out", default="eval/results.jsonl")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--dump", default=None, help="write per-utterance details (pred, latency, errors) to this JSONL")
    ap.add_argument("--rescore", default=None, help="score the predictions saved in this --dump file (no model calls)")
    ap.add_argument("--ids", default=None, help="score only these ids: a range like v1_001-v1_050")
    ap.add_argument("--gfast-gold", default=None, help="G.F.A.S.T. labels (eval/gold_v*_gfast.jsonl), scored separately")
    ap.add_argument("--group-gold", action="append", default=[], metavar="GROUP=FILE",
                    help="labels for a key group in eval/scoring.yaml (e.g. broad=eval/gold_v2_broad.jsonl)")
    a = ap.parse_args()

    rows = [json.loads(line) for line in open(a.gold) if line.strip()]
    if a.ids:
        lo, hi = a.ids.split("-")
        rows = [r for r in rows if lo <= r["id"] <= hi]
    if a.rescore:
        first = json.loads(open(a.rescore).readline())
        label = first.get("label") or first["extractor"]
        items = replay(a.rescore, rows)
    else:
        name = a.model or build_extractor("rules", None)[2].model_name()
        label = {"rules": "rules", "llm": f"llm:{name}", "pipeline": f"rules+llm:{name}"}[a.extractor]
        items = predict(a, rows)
    TP = FP = FN = ROLE = 0
    FT = [0, 0, 0]
    gfast_gold = ({d["id"]: d["gfast"] for d in map(json.loads, open(a.gfast_gold))} if a.gfast_gold else None)
    GF = [0, 0, 0]
    group_gold = {}
    for spec in a.group_gold:
        name, path = spec.split("=", 1)
        group_gold[name] = {d["id"]: d.get("facts", d.get(name, [])) for d in map(json.loads, open(path))}
    GG = {name: [0, 0, 0] for name in group_gold}
    dump = open(a.dump, "w") if a.dump else None
    lat, invalid, out_tokens = [], 0, []
    for r, pred, ms, tokens, err in items:
        lat.append(ms)
        invalid += err is not None
        if tokens is not None:
            out_tokens.append(tokens)
        if err and a.verbose:
            print(f"  {r['id']} ERROR {err}")
        tp, fp, fn, role_ok, extra, missed = score(r["facts"], pred)
        ft = score(r["facts"], pred, free_text=True)
        FT = [FT[0] + ft[0], FT[1] + ft[1], FT[2] + ft[2]]
        if gfast_gold is not None:
            g = atoms([tuple(x[:3]) for x in gfast_gold.get(r["id"], [])])
            p = atoms([x for x in pred if x[0].startswith(SEPARATE_PREFIX)])
            GF = [GF[0] + len(set(g) & set(p)), GF[1] + len(set(p) - set(g)), GF[2] + len(set(g) - set(p))]
        for name, gold_g in group_gold.items():
            g = group_atoms([tuple(x[:3]) for x in gold_g.get(r["id"], []) if group_of(x[0]) == name])
            p = group_atoms([x for x in pred if group_of(x[0]) == name])
            c = GG[name]
            GG[name] = [c[0] + len(set(g) & set(p)), c[1] + len(set(p) - set(g)), c[2] + len(set(g) - set(p))]
        if dump:
            dump.write(json.dumps({"id": r["id"], "extractor": a.extractor, "label": label, "ms": round(ms),
                                   "tokens": tokens, "error": err, "pred": [list(x) for x in pred],
                                   "extra": [list(x) for x in extra], "missed": [list(x) for x in missed]},
                                  default=str) + "\n")
        TP, FP, FN, ROLE = TP + tp, FP + fp, FN + fn, ROLE + role_ok
        if a.verbose and (extra or missed):
            print(f"  {r['id']}: extra={extra} missed={missed}")
    P = TP / (TP + FP) if TP + FP else 0.0
    R = TP / (TP + FN) if TP + FN else 0.0
    F1 = 2 * P * R / (P + R) if P + R else 0.0
    lat_sorted = sorted(lat)
    ftp, ffp, ffn = FT
    ft_f1 = (2 * ftp / (2 * ftp + ffp + ffn)) if (ftp + ffp + ffn) else 0.0
    res = {
        "extractor": label, "gold": a.gold + (f"[{a.ids}]" if a.ids else ""), "scorer": "v2",
        "rescored_from": a.rescore, "n": len(rows),
        "precision": round(P, 3), "recall": round(R, 3), "f1": round(F1, 3),
        "role_acc": round(ROLE / TP, 3) if TP else 0.0, "json_invalid": invalid,
        "free_text_presence_f1": round(ft_f1, 3),
        **({"gfast_precision": round(GF[0] / (GF[0] + GF[1]), 3) if GF[0] + GF[1] else 0.0,
            "gfast_recall": round(GF[0] / (GF[0] + GF[2]), 3) if GF[0] + GF[2] else 0.0,
            "gfast_f1": round(2 * GF[0] / (2 * GF[0] + GF[1] + GF[2]), 3) if GF[0] else 0.0,
            "gfast_counts": {"tp": GF[0], "fp": GF[1], "fn": GF[2]}} if gfast_gold is not None else {}),
        **({"groups": {n: {"precision": round(c[0] / (c[0] + c[1]), 3) if c[0] + c[1] else 0.0,
                           "recall": round(c[0] / (c[0] + c[2]), 3) if c[0] + c[2] else 0.0,
                           "f1": round(2 * c[0] / (2 * c[0] + c[1] + c[2]), 3) if c[0] else 0.0,
                           "counts": {"tp": c[0], "fp": c[1], "fn": c[2]}} for n, c in GG.items()}} if GG else {}),
        "first_call_ms": round(lat[0]),
        "latency_ms_p50": round(statistics.median(lat)), "latency_ms_p95": round(lat_sorted[int(0.95 * (len(lat) - 1))]),
        "out_tokens_avg": round(statistics.mean(out_tokens), 1) if out_tokens else None,
        "decode_tok_s": (round(sum(out_tokens) / (sum(lat) / 1000), 1) if out_tokens and sum(lat) else None),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(json.dumps(res))
    with open(a.out, "a") as fh:
        fh.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()
