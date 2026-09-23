#!/usr/bin/env python3
"""Extraction benchmark: same gold set, same scoring, any extractor.

  python eval/bench_extract.py --extractor rules
  python eval/bench_extract.py --extractor llm --model omni          # a model served by ZRT on :8080
  python eval/bench_extract.py --extractor llm --model omni --gold eval/gold_v0.jsonl --out eval/results.jsonl

Scores (key, value) pairs: precision / recall / F1, role accuracy on matched facts,
JSON validity, and per-utterance latency. Numbers go straight into the deck.
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herald import extract_rules  # noqa: E402
from herald.schema import CapturedBy, Role  # noqa: E402


def norm(key, v):
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


def score(gold, pred):
    g = {(k, norm(k, v)): r for k, v, r in gold}
    p = {}
    for f in pred:
        p[(f.key, norm(f.key, f.value))] = f.role.value
    tp = set(g) & set(p)
    role_ok = sum(1 for x in tp if g[x] == p[x])
    return len(tp), len(p) - len(tp), len(g) - len(tp), role_ok, sorted(set(p) - set(g)), sorted(set(g) - set(p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["rules", "llm"], default="rules")
    ap.add_argument("--model", default=None, help="served model name (ZRT label)")
    ap.add_argument("--gold", default="eval/gold_v0.jsonl")
    ap.add_argument("--out", default="eval/results.jsonl")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.model:
        os.environ["HERALD_LLM_MODEL"] = a.model
    from herald import extract_llm, llm  # import after env is set

    rows = [json.loads(line) for line in open(a.gold) if line.strip()]
    TP = FP = FN = ROLE = 0
    lat, invalid, out_tokens = [], 0, []
    for r in rows:
        by = CapturedBy(r.get("by", "medic"))
        role = Role.family if by == CapturedBy.other else Role.medic
        t0 = time.perf_counter()
        try:
            if a.extractor == "rules":
                pred = extract_rules.extract(r["text"], by, role, r.get("speaker"))
            else:
                pred = extract_llm.extract(r["text"], by, role, r.get("speaker"))
                out_tokens.append(getattr(extract_llm.extract, "last_usage", {}).get("completion_tokens", 0))
        except Exception as e:
            pred, invalid = [], invalid + 1
            if a.verbose:
                print(f"  {r['id']} ERROR {e}")
        lat.append((time.perf_counter() - t0) * 1000)
        tp, fp, fn, role_ok, extra, missed = score(r["facts"], pred)
        TP, FP, FN, ROLE = TP + tp, FP + fp, FN + fn, ROLE + role_ok
        if a.verbose and (extra or missed):
            print(f"  {r['id']}: extra={extra} missed={missed}")
    P = TP / (TP + FP) if TP + FP else 0.0
    R = TP / (TP + FN) if TP + FN else 0.0
    F1 = 2 * P * R / (P + R) if P + R else 0.0
    lat_sorted = sorted(lat)
    res = {
        "extractor": a.extractor if a.extractor == "rules" else f"llm:{llm.model_name()}",
        "gold": a.gold, "n": len(rows), "precision": round(P, 3), "recall": round(R, 3), "f1": round(F1, 3),
        "role_acc": round(ROLE / TP, 3) if TP else 0.0, "json_invalid": invalid,
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
