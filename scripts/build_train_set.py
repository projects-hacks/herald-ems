#!/usr/bin/env python3
"""Build a fine-tuning set from annotated utterances (data/annotated/batch_*.jsonl) plus composed rows.

  python scripts/build_train_set.py --out data/train_b --composed 1200
  python scripts/build_train_set.py --out data/train_d --composed 1200 --order spoken --profile ems-d   # run D

Annotated rows are written by independent annotators under docs/LABELING_GUIDE.md, cover every key in
KEYS, and never see eval/. Composed rows (scripts/compose_synth.py) add numeric and noise variety.
Every row is validated against KEYS before use; a row that fails is dropped and counted. The completion
format is what the served extractor parses: {"f": [[key, value, who], ...]} with who = m, p, b, f:<relation>.

--order spoken puts every target's facts in the order they were said (config/training.yaml): a consistent order
removes the "which fact comes next" uncertainty that lowered per-fact confidence (MODEL_PLAN §0g).
--profile builds the model input exactly as the served extractor will send it (herald/extraction/profiles.py),
e.g. with the speaker line for run D.
"""
import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from herald.config import load_yaml  # noqa: E402
from herald.core.vocabulary import default_vocabulary  # noqa: E402
from herald.extraction.grounding import default_grounding  # noqa: E402
from herald.extraction.profiles import default_profiles  # noqa: E402

VOCAB = default_vocabulary()
KEYS = VOCAB.keys

WHO = {"medic": "m", "patient": "p", "bystander": "b"}


def who_code(role: str, source, speaker) -> str:
    if role == "family":
        return f"f:{(source or speaker or 'family').strip().lower()}"
    return WHO[role]


class SpokenOrder:
    """Sort a target's facts by where the utterance first supports each one (config/training.yaml)."""

    def __init__(self, cfg: dict):
        g = default_grounding()
        self.numbers = g.spoken
        self.cues = {k: re.compile(v, re.I) for k, v in cfg["order_cues"].items()}
        self.cues = {**g.requires, **self.cues}
        self.same_place = cfg["same_place_order"]
        self.located = self.total = self.reordered = 0

    def _where(self, text: str, key: str, value) -> int | None:
        low = text.lower()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            spots = [m.start() for m in re.finditer(r"\d+(?:\.\d+)?", text) if abs(float(m.group()) - value) < 0.05]
            spots += [s for s, vals in self.numbers.spans(text) if any(abs(v - value) < 0.05 for v in vals)]
            if spots:
                return min(spots)
        elif isinstance(value, (str, list)) and not (isinstance(value, str) and value.lower() == "none"):
            spots = []
            for item in (value if isinstance(value, list) else [value]):
                s = str(item).lower().strip()
                i = low.find(s) if len(s) >= 3 else -1
                if i < 0:
                    words = [w for w in re.findall(r"[a-z]{4,}", s)]
                    hits = [m.start() for w in words[:1] for m in [re.search(rf"\b{re.escape(w)}", low)] if m]
                    i = hits[0] if hits else -1
                if i >= 0:
                    spots.append(i)
            if spots:
                return min(spots)
        cue = self.cues.get(key)
        m = cue.search(text) if cue else None
        return m.start() if m else None

    def _rank(self, key: str) -> int:
        return next((i for i, p in enumerate(self.same_place) if key.startswith(p)), len(self.same_place))

    def sort(self, text: str, rows: list) -> list:
        placed, last = [], -1.0
        for idx, row in enumerate(rows):
            pos = self._where(text, row[0], row[1])
            self.total += 1
            if pos is None:
                pos = last + 1e-3                    # keeps its place after the fact before it
            else:
                self.located += 1
            last = pos
            placed.append((pos, self._rank(row[0]), idx, row))
        out = [r for *_, r in sorted(placed, key=lambda x: x[:3])]
        self.reordered += out != rows
        return out


def word_runs(text: str, n: int = 8) -> set:
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def model_input(profile_prefix: str | None, text: str, by: str, speaker) -> str:
    profiles = default_profiles()
    profile = profiles.for_label(profile_prefix) if profile_prefix else None
    return profiles.model_input(profile, text, by, speaker)


def annotated_row(r: dict) -> dict:
    out = []
    for fact in r["facts"]:
        k, v, role = fact[0], fact[1], fact[2]
        source = fact[3] if len(fact) > 3 else None
        if k not in KEYS or role not in ("medic", "patient", "family", "bystander"):
            raise ValueError(f"bad key/role {k}/{role}")
        VOCAB.coerce(k, v)
        out.append([k, v, who_code(role, source, r.get("speaker"))])
    return {"id": r["id"], "text": r["text"], "by": r.get("by", "medic"), "speaker": r.get("speaker"),
            "source": "annotated", "rows": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotated", default=str(ROOT / "data" / "annotated"))
    ap.add_argument("--composed", type=int, default=1200, help="how many composed rows to mix in (0 = none)")
    ap.add_argument("--composed-file", default=str(ROOT / "data" / "synth" / "train.jsonl"))
    ap.add_argument("--dev-frac", type=float, default=0.1)
    ap.add_argument("--out", default=str(ROOT / "data" / "train_b"))
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--order", choices=["as_labeled", "spoken"], default="as_labeled")
    ap.add_argument("--decontaminate", default="", help="comma-separated gold files: drop any row sharing an "
                    "8-word run with them (the held-out sets must stay unseen)")
    ap.add_argument("--profile", default=None, help="served-label prefix whose input format to build (e.g. ems-d)")
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
    gold_grams = set().union(*(word_runs(json.loads(l)["text"]) for f in filter(None, a.decontaminate.split(","))
                               for l in open(f)))
    n_before = len(ann)
    ann = [r for r in ann if not (word_runs(r["text"]) & gold_grams)]
    dropped["overlaps a gold set (8-word run)"] += n_before - len(ann)
    rng.shuffle(ann)
    n_dev = int(len(ann) * a.dev_frac)
    dev, train = ann[:n_dev], ann[n_dev:]

    if a.composed:
        comp = [json.loads(l) for l in open(a.composed_file)]
        rng.shuffle(comp)
        comp = [r for r in comp if not (word_runs(r["text"]) & gold_grams)]
        train += [{"id": f"c{i}", "text": r["text"], "by": r.get("by", "medic"), "speaker": r.get("speaker"),
                   "source": "composed", "rows": json.loads(r["completion"])["f"]}
                  for i, r in enumerate(comp[:a.composed])]
    rng.shuffle(train)

    order = SpokenOrder(load_yaml("training.yaml")) if a.order == "spoken" else None
    for r in train + dev:
        rows = order.sort(r["text"], r.pop("rows")) if order else r.pop("rows")
        r["completion"] = json.dumps({"f": rows}, separators=(",", ":"), ensure_ascii=False)
        r["raw_text"] = r["text"]
        r["text"] = model_input(a.profile, r["text"], r["by"], r["speaker"])

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("dev", dev)):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    keys = Counter(f[0] for r in train for f in json.loads(r["completion"])["f"])
    print(json.dumps({"annotated": len(ann), "overlay_items": len(overlay), "train": len(train), "dev (annotated only)": len(dev),
                      "composed": sum(r["source"] == "composed" for r in train),
                      "order": a.order, "profile": a.profile,
                      **({"facts_located": f"{order.located}/{order.total}", "targets_reordered": order.reordered}
                         if order else {}),
                      "dropped": dict(dropped), "keys_covered": f"{len(keys)}/{len(KEYS)}",
                      "missing_keys": sorted(set(KEYS) - set(keys))}, indent=1))


if __name__ == "__main__":
    main()
