#!/usr/bin/env python3
"""Inter-annotator agreement for two independently labeled gold files.

  python eval/agreement.py eval/gold_v1_labeler_a.jsonl eval/gold_v1_labeler_b.jsonl [--disagreements out.jsonl]

Agreement is fact-level F1 between the two label sets on (key, normalized value), using the same
normalization as the benchmark (structured keys exact; free-text keys by presence). It is symmetric.
Also reports role agreement on matched facts, per-key and per-phenomenon agreement, and writes every
disagreement for adjudication. Adjudicate BEFORE running any extractor on the set.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_extract import FREE_TEXT, norm  # noqa: E402


def pairs(facts):
    out = {}
    for k, v, r in facts:
        out[(k, None) if k in FREE_TEXT else (k, norm(k, v))] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--disagreements", default=None)
    x = ap.parse_args()
    A = {r["id"]: r for r in map(json.loads, open(x.a)) if r}
    B = {r["id"]: r for r in map(json.loads, open(x.b)) if r}
    assert A.keys() == B.keys(), "id mismatch"
    tp = fa = fb = role_ok = 0
    per_key = defaultdict(lambda: [0, 0, 0])
    per_ph = defaultdict(lambda: [0, 0, 0])
    items_equal = 0
    dis = []
    for i in sorted(A):
        pa, pb = pairs(A[i]["facts"]), pairs(B[i]["facts"])
        both, only_a, only_b = set(pa) & set(pb), set(pa) - set(pb), set(pb) - set(pa)
        tp += len(both); fa += len(only_a); fb += len(only_b)
        role_ok += sum(1 for k in both if pa[k] == pb[k])
        role_diff = [k for k in both if pa[k] != pb[k]]
        for k in both: per_key[k[0]][0] += 1
        for k in only_a: per_key[k[0]][1] += 1
        for k in only_b: per_key[k[0]][2] += 1
        for ph in A[i].get("phenomena", []):
            per_ph[ph][0] += len(both); per_ph[ph][1] += len(only_a); per_ph[ph][2] += len(only_b)
        if not only_a and not only_b and not role_diff:
            items_equal += 1
        else:
            dis.append({"id": i, "text": A[i]["text"], "only_a": sorted(map(list, only_a), key=str),
                        "only_b": sorted(map(list, only_b), key=str),
                        "role_diff": [[k[0], k[1], pa[k], pb[k]] for k in role_diff],
                        "notes_a": A[i].get("notes"), "notes_b": B[i].get("notes")})
    f1 = 2 * tp / (2 * tp + fa + fb) if tp + fa + fb else 1.0
    print(json.dumps({"items": len(A), "items_identical": items_equal, "fact_f1": round(f1, 3),
                      "agreed_facts": tp, "only_a": fa, "only_b": fb,
                      "role_agreement": round(role_ok / tp, 3) if tp else None}))
    print("\nper key (agree / only A / only B), worst first:")
    for k, (t, a, b) in sorted(per_key.items(), key=lambda kv: -(kv[1][1] + kv[1][2])):
        if a or b:
            print(f"  {k:28} {t:3} / {a:2} / {b:2}")
    print("\nper phenomenon fact F1:")
    for ph, (t, a, b) in sorted(per_ph.items()):
        print(f"  {ph:16} {2 * t / (2 * t + a + b) if t + a + b else 1:.3f}  (n agree {t}, A-only {a}, B-only {b})")
    if x.disagreements:
        with open(x.disagreements, "w") as fh:
            for d in dis:
                fh.write(json.dumps(d, default=str) + "\n")
        print(f"\n{len(dis)} items with disagreements -> {x.disagreements}")


if __name__ == "__main__":
    main()
