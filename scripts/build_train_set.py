#!/usr/bin/env python3
"""Build a fine-tuning set from annotated utterances (data/annotated/batch_*.jsonl) plus composed rows.

  python scripts/build_train_set.py --out data/train_b --composed 1200

Annotated rows are written by independent annotators under docs/LABELING_GUIDE.md, cover every key in
KEYS, and never see eval/. Composed rows (scripts/compose_synth.py) add numeric and noise variety.
Every row is validated against KEYS before use; a row that fails is dropped and counted. The completion
format is what the served extractor parses: {"f": [[key, value, who], ...]} with who = m, p, b, f:<relation>.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from herald.core.vocabulary import default_vocabulary  # noqa: E402

VOCAB = default_vocabulary()
KEYS = VOCAB.keys

WHO = {"medic": "m", "patient": "p", "bystander": "b"}


def who_code(role: str, source, speaker) -> str:
    if role == "family":
        return f"f:{(source or speaker or 'family').strip().lower()}"
    return WHO[role]


def annotated_row(r: dict) -> dict:
    out = []
    for fact in r["facts"]:
        k, v, role = fact[0], fact[1], fact[2]
        source = fact[3] if len(fact) > 3 else None
        if k not in KEYS or role not in ("medic", "patient", "family", "bystander"):
            raise ValueError(f"bad key/role {k}/{role}")
        VOCAB.coerce(k, v)
        out.append([k, v, who_code(role, source, r.get("speaker"))])
    return {"id": r["id"], "text": r["text"], "source": "annotated",
            "completion": json.dumps({"f": out}, separators=(",", ":"), ensure_ascii=False)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotated", default=str(ROOT / "data" / "annotated"))
    ap.add_argument("--composed", type=int, default=1200, help="how many composed rows to mix in (0 = none)")
    ap.add_argument("--composed-file", default=str(ROOT / "data" / "synth" / "train.jsonl"))
    ap.add_argument("--dev-frac", type=float, default=0.1)
    ap.add_argument("--out", default=str(ROOT / "data" / "train_b"))
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    rng = random.Random(a.seed)

    # Label overlays add keys labeled after a batch was written (e.g. G.F.A.S.T., LABELING_GUIDE §4d):
    # gfast_labels_*.jsonl lines are {"id": ..., "gfast": [[key, value, role, source], ...]}.
    overlay: dict[str, list] = {}
    for f in sorted(Path(a.annotated).glob("gfast_labels_*.jsonl")):
        for line in open(f):
            d = json.loads(line)
            overlay.setdefault(d["id"], []).extend(d.get("gfast", []))
    ann, dropped = [], Counter()
    for f in sorted(Path(a.annotated).glob("batch_*.jsonl")):
        for line in open(f):
            try:
                r = json.loads(line)
                have = {(x[0], json.dumps(x[1], sort_keys=True)) for x in r["facts"]}
                r["facts"] = r["facts"] + [x for x in overlay.get(r["id"], [])
                                           if (x[0], json.dumps(x[1], sort_keys=True)) not in have]
                ann.append(annotated_row(r))
            except Exception as e:
                dropped[f"{f.name}: {type(e).__name__}"] += 1
    texts = set()
    ann = [r for r in ann if not (r["text"] in texts or texts.add(r["text"]))]
    rng.shuffle(ann)
    n_dev = int(len(ann) * a.dev_frac)
    dev, train = ann[:n_dev], ann[n_dev:]

    if a.composed:
        comp = [json.loads(l) for l in open(a.composed_file)]
        rng.shuffle(comp)
        train += [{"id": f"c{i}", "text": r["text"], "source": "composed", "completion": r["completion"]}
                  for i, r in enumerate(comp[:a.composed])]
    rng.shuffle(train)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("dev", dev)):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    keys = Counter(f[0] for r in train for f in json.loads(r["completion"])["f"])
    print(json.dumps({"annotated": len(ann), "overlay_items": len(overlay), "train": len(train), "dev (annotated only)": len(dev),
                      "composed": sum(r["source"] == "composed" for r in train),
                      "dropped": dict(dropped), "keys_covered": f"{len(keys)}/{len(KEYS)}",
                      "missing_keys": sorted(set(KEYS) - set(keys))}, indent=1))


if __name__ == "__main__":
    main()
