#!/usr/bin/env python3
"""Add real-California-POLST photos (render_polst.py) to the vision training set and write a held-out test set.

  python scripts/vision_train/make_polst.py --train 240 --dev 20 --test 60

- train: font groups 0-2, appended to data/vision_train/train.jsonl (ids polst_train_*), same row schema as make.py;
- dev: held-out font group 3, appended to dev.jsonl;
- test: held-out font group 3 on a separate seed, written to eval/forms_polst/ (images + gold.jsonl in the
  data/photos/real/labels.jsonl format, so eval/vision_bench.py --gold scores it). Never trained on.

A photo is re-taken when its answer names a checked box but the photo would not let a reader see the tick: motion
blur or blur, or the answer box under 14 px tall in the photo. The prompt says to omit what is not clearly visible,
so such a photo with a non-empty answer would teach guessing. Re-running replaces earlier polst_* rows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.vision_train import targets  # noqa: E402
from scripts.vision_train.make import _truth  # noqa: E402
from scripts.vision_train.photo import photograph  # noqa: E402
from scripts.vision_train.render_polst import ca_polst  # noqa: E402

FAMILY = "ca_polst"
MIN_BOX_PX = 14
BLURS = {"blur", "motion_blur"}
TEST_SEED = 424_242


def legible(ex) -> bool:
    for r in ex.panel.readings:
        if r.readable and r.box:
            short = min((r.box[2] - r.box[0]) * ex.image.width, (r.box[3] - r.box[1]) * ex.image.height)
            need = MIN_BOX_PX + (8 if any("faint" in n for n in ex.panel.notes) else 0)
            if BLURS & set(ex.degradations) or short < need:     # the short side: rotation swaps width and height
                return False
    return True


def one(split: str, i: int, seed: int, variants: list[int], prompts):
    for attempt in range(40):
        rng = Random(f"{seed}:{split}:{i}:{attempt}")
        variant = rng.choice(variants)
        panel = ca_polst(rng, variant)
        ex = photograph(panel, rng, f"polst_{split}_{i:04d}", hard=rng.uniform(0.0, 0.6))
        if legible(ex):
            return ex, variant, f"{seed}:{split}:{i}:{attempt}"
    raise RuntimeError(f"no legible photo for {split} {i}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=int, default=240)
    ap.add_argument("--dev", type=int, default=20)
    ap.add_argument("--test", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/vision_train")
    ap.add_argument("--test-out", default="eval/forms_polst")
    a = ap.parse_args()
    p = targets.Prompts.load()
    out, tout = ROOT / a.out, ROOT / a.test_out
    counts: dict = {}
    for split, n, seed, variants in (("train", a.train, a.seed, [0, 1, 2]), ("dev", a.dev, a.seed + 1_000_003, [3])):
        rows = []
        for i in range(n):
            ex, variant, sd = one(split, i, seed, variants, p)
            rel = Path(a.out) / "images" / split / f"{ex.id}.jpg"
            (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / rel).write_bytes(ex.jpeg)
            answer = targets.dumps(targets.build("form", ex.panel.readings, ex.severity, p))
            rows.append({"id": ex.id, "split": split, "image": str(rel), "width": ex.image.width,
                         "height": ex.image.height, "mode": "form", "family": FAMILY, "layout": ex.panel.family,
                         "variant": variant, "device": ex.panel.device, "seed": sd, "degradations": ex.degradations,
                         "severity": round(ex.severity, 3), "system": p.system, "user": p.modes["form"],
                         "prompt_sha": p.sha, "target": answer,
                         "messages": targets.messages(p.system, p.modes["form"], str(rel), answer),
                         "truth": _truth(ex.panel.readings), "texts": ex.panel.texts,
                         "distractors": ex.panel.distractors, "notes": ex.panel.notes})
            key = (split, ex.panel.notes[0], answer != '{"facts":[]}')
            counts[str(key)] = counts.get(str(key), 0) + 1
        path = out / f"{split}.jsonl"
        kept = [ln for ln in path.read_text().splitlines() if ln and json.loads(ln)["family"] != FAMILY]
        path.write_text("\n".join(kept + [json.dumps(r, ensure_ascii=False) for r in rows]) + "\n")
    tout.mkdir(parents=True, exist_ok=True)
    gold = []
    for i in range(a.test):
        ex, variant, sd = one("test", i, TEST_SEED, [3], p)
        (tout / f"{ex.id}.jpg").write_bytes(ex.jpeg)
        facts = {r.key: r.value for r in ex.panel.readings if r.readable}
        gold.append({"file": f"{ex.id}.jpg", "mode": "form", "device": ex.panel.family, "facts": facts,
                     "ignore": ex.panel.distractors, "note": "; ".join(ex.panel.notes), "seed": sd,
                     "degradations": ex.degradations})
        counts[str(("test", ex.panel.notes[0], bool(facts)))] = counts.get(str(("test", ex.panel.notes[0], bool(facts))), 0) + 1
    (tout / "gold.jsonl").write_text("".join(json.dumps(g) + "\n" for g in gold))
    print(json.dumps(dict(sorted(counts.items())), indent=0))


if __name__ == "__main__":
    main()
