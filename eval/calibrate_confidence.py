#!/usr/bin/env python3
"""Calibrate the auto-confirm threshold on the model's per-fact confidence (token probabilities).

  python eval/calibrate_confidence.py --model ems-c-fp8 --gold eval/gold_v1.jsonl            # dev: choose
  python eval/calibrate_confidence.py --model ems-c-fp8 --gold eval/gold_v2.jsonl --threshold T  # held-out: verify
  python eval/calibrate_confidence.py --rescore eval/dumps/gold_v2/calibration_ems_d_fp8_joint.jsonl \
      --gold eval/gold_v2.jsonl --terminology on --threshold 0.8          # the same facts after drug coding

A fact counts as correct when its value (per list item) matches the gold labels AND it is attributed to the right
person. Only facts from the medic's own mic (by: medic) are eligible: other speakers never auto-confirm. For each
threshold: precision of the auto-confirmed facts, coverage (share of eligible facts that skip the tap), and the
number of wrong facts that would confirm themselves. A fact held for a tap (a drug name matched only by spelling
or sound, `provenance.hold_reason`) never confirms itself, whatever its confidence.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_extract import FREE_TEXT, atoms, build_coder  # noqa: E402
from herald.config import Settings  # noqa: E402
from herald.core.schema import CapturedBy, FactIn, Role  # noqa: E402
from herald.core.vocabulary import default_vocabulary  # noqa: E402
from herald.extraction import ModelExtractor  # noqa: E402
from herald.models import LocalLLMClient  # noqa: E402

THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99]


def correct(f, gold_facts) -> bool:
    if f.key in FREE_TEXT:
        return any(k == f.key and r == f.role.value for k, v, r in gold_facts)
    g = atoms([tuple(x) for x in gold_facts if x[0] == f.key])
    mine = atoms([(f.key, f.value, f.role.value)])
    return bool(mine) and all(a in g and g[a] == r for a, r in mine.items())


def table(records, thresholds):
    rows = []
    for t in thresholds:
        auto = [r for r in records if r["conf"] >= t and not r.get("held")]
        wrong = sum(1 for r in auto if not r["correct"])
        rows.append({"threshold": t, "auto_confirmed": len(auto), "wrong_auto": wrong,
                     "precision": round(1 - wrong / len(auto), 3) if auto else None,
                     "coverage": round(len(auto) / len(records), 3) if records else 0})
    return rows


def auroc(records) -> float:
    pos = [r["conf"] for r in records if r["correct"]]
    neg = [r["conf"] for r in records if not r["correct"]]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="served label (live run; not needed with --rescore)")
    ap.add_argument("--rescore", default=None, help="replay the facts saved in this --dump file (no model calls)")
    ap.add_argument("--terminology", choices=["on", "off"], default=None,
                    help="drug coding (default: on for live runs, as the app wires it; off for --rescore)")
    ap.add_argument("--gold", required=True)
    ap.add_argument("--threshold", type=float, default=None, help="report this threshold (held-out verification)")
    ap.add_argument("--dump", default=None)
    ap.add_argument("--gfast-gold", default=None, help="G.F.A.S.T. labels for the same set (they live in a separate file)")
    ap.add_argument("--mode", default="joint", choices=["joint", "value", "order_free", "min", "mean"])
    a = ap.parse_args()
    if not a.model and not a.rescore:
        ap.error("--model or --rescore is required")
    s = Settings.from_env()
    vocab = default_vocabulary()
    coder = build_coder((a.terminology or ("off" if a.rescore else "on")) == "on")
    saved: dict[str, list[dict]] = {}
    if a.rescore:
        for r in map(json.loads, open(a.rescore)):
            saved.setdefault(r["id"], []).append(r)

        def extract(g):
            facts = [FactIn(key=r["key"], value=r["value"], role=Role(r["role"]), captured_by=CapturedBy.medic,
                            confidence=r["conf"]) for r in saved.get(g["id"], [])]
            return coder.code(facts) if coder else facts
    else:
        x = ModelExtractor(LocalLLMClient(s.llm_url, a.model), finetuned_labels=s.finetuned_models,
                           confidence_mode=a.mode, coder=coder)

        def extract(g):
            return x.extract(g["text"], CapturedBy.medic, Role.medic, g.get("speaker"), dispatch=g.get("dispatch"))
    gfast = ({d["id"]: [x[:3] for x in d["gfast"]] for d in map(json.loads, open(a.gfast_gold))}
             if a.gfast_gold else None)
    records = []
    for line in open(a.gold):
        g = json.loads(line)
        if gfast is not None:
            g["facts"] = g["facts"] + gfast.get(g["id"], [])
        if g.get("by", "medic") != "medic":
            continue
        for f in extract(g):
            if vocab.meta(f.key).get("require_tap"):
                continue                      # code status always waits for a tap
            if gfast is None and f.key.startswith("exam.gfast."):
                continue                      # no labels to judge it against
            records.append({"id": g["id"], "key": f.key, "value": f.value, "role": f.role.value,
                            "conf": f.confidence, "correct": correct(f, g["facts"]),
                            "held": bool(f.provenance.hold_reason)})
    if a.dump:
        Path(a.dump).write_text("".join(json.dumps(r, default=str) + "\n" for r in records))
    n_wrong = sum(1 for r in records if not r["correct"])
    print(json.dumps({"gold": a.gold, "model": a.model, "rescored_from": a.rescore, "mode": a.mode,
                      "terminology": coder.release if coder else None, "eligible_facts": len(records),
                      "wrong_facts": n_wrong, "held_for_tap": sum(1 for r in records if r["held"]),
                      "auroc": auroc(records)}))
    for row in table(records, [a.threshold] if a.threshold else THRESHOLDS):
        print(json.dumps(row))


if __name__ == "__main__":
    main()
