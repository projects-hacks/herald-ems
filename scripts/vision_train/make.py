#!/usr/bin/env python3
"""Build the vision training set (docs/MODEL_PLAN.md §2a "Vision training set"). CPU only; no model calls.

  python scripts/vision_train/make.py --n 3500 --seed 7 --out data/vision_train/
  python scripts/vision_train/make.py --retarget --out data/vision_train/     # after a vision prompt edit

Writes <out>/images/{train,dev}/*.jpg, <out>/train.jsonl, <out>/dev.jsonl and <out>/manifest.json. Each record
holds the image path, the capture mode, the production system and user prompt for that mode (read from
config/prompts/vision.yaml at build time), the exact target JSON, the chat `messages`, and the truth behind the
target (every reading, readable or not, with its box) so `--retarget` can re-render prompts and targets from the
current config without re-rendering images. Every target is checked through the product's VisionReader (with
the RxNorm coder when the index is built) before it is written."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from random import Random
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.vision_train import families, targets  # noqa: E402
from scripts.vision_train.decontam import Exclusions  # noqa: E402
from scripts.vision_train.photo import photograph  # noqa: E402
from scripts.vision_train.spec import Reading  # noqa: E402
from scripts.vision_train.validate import ReaderCheck  # noqa: E402

DEV_SEED_OFFSET = 1_000_003          # dev examples draw from a separate seed stream
GENTLE_SHARE = 0.2                   # photos with no fingers, glare, blur or low light
_W: dict = {}


def _init_worker(index_path: str) -> None:
    from scripts.vision_train.drugs import build_catalog, load_normalizer
    p = Path(index_path)
    ex = Exclusions()
    if p.exists():
        cat = build_catalog(p, load_normalizer(p))
        cat.exclude(ex.drug_strengths)
        _W["catalog"] = cat
    else:
        _W["catalog"] = None
    _W["excl"] = ex
    _W["prompts"] = targets.Prompts.load()


def _truth(readings: list[Reading]) -> list[dict]:
    return [{k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(r).items()} for r in readings]


def make_one(job: tuple, seed: int, out: str) -> dict:
    split, i, fam_name = job
    fam = families.BY_NAME[fam_name]
    base = seed + (DEV_SEED_OFFSET if split == "dev" else 0)
    for attempt in range(20):
        rng = Random(f"{base}:{split}:{i}:{attempt}")
        variant = rng.choice(sorted(fam.dev) if split == "dev" else fam.train_variants())
        panel = families.render(fam_name, rng, variant, _W["catalog"])
        hard = 0.0 if rng.random() < GENTLE_SHARE else rng.uniform(0.15, 1.0)
        ex = photograph(panel, rng, f"{split}_{i:05d}", hard=hard)
        target = targets.build(panel.mode, panel.readings, ex.severity, _W["prompts"])
        facts = [(f["key"], f["value"]) for f in target["facts"]]
        if panel.mode == "monitor" and facts and _W["excl"].monitor_collides(panel.device, facts):
            continue                                   # same readings as a test photo of this kind: re-roll
        break
    base_dir = Path(out).resolve()
    base_dir = base_dir.relative_to(ROOT) if base_dir.is_relative_to(ROOT) else base_dir   # repo-relative when inside
    img_rel = base_dir / "images" / split / f"{ex.id}.jpg"
    (ROOT / img_rel).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / img_rel).write_bytes(ex.jpeg)
    p = _W["prompts"]
    answer = targets.dumps(target)
    return {"id": ex.id, "split": split, "image": str(img_rel), "width": ex.image.width, "height": ex.image.height,
            "mode": panel.mode, "family": fam_name, "layout": panel.family, "variant": variant, "device": panel.device,
            "seed": f"{base}:{split}:{i}:{attempt}", "degradations": ex.degradations, "severity": round(ex.severity, 3),
            "system": p.system, "user": p.modes[panel.mode], "prompt_sha": p.sha, "target": answer,
            "messages": targets.messages(p.system, p.modes[panel.mode], str(img_rel), answer),
            "truth": _truth(panel.readings), "texts": panel.texts, "distractors": panel.distractors, "notes": panel.notes}


def retarget(out: Path, index: Optional[Path] = None) -> None:
    """Re-read the prompts from config and rebuild every record's prompt text and target from its truth, then
    re-check every target through the reader and record the new prompt hash in the manifest."""
    p = targets.Prompts.load()
    everything = []
    for split in ("train", "dev"):
        path = out / f"{split}.jsonl"
        recs = [json.loads(x) for x in open(path)]
        for r in recs:
            readings = [Reading(**{k: (tuple(v) if isinstance(v, list) and k.endswith("box") else v)
                                   for k, v in t.items()}) for t in r["truth"]]
            answer = targets.dumps(targets.build(r["mode"], readings, r["severity"], p))
            r.update(system=p.system, user=p.modes[r["mode"]], prompt_sha=p.sha, target=answer,
                     messages=targets.messages(p.system, p.modes[r["mode"]], r["image"], answer))
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
        everything += recs
    check = ReaderCheck(index).run(everything)
    mpath = out / "manifest.json"
    if mpath.exists():
        m = json.loads(mpath.read_text())
        m.update(prompt_sha=p.sha, reader_check=check, retargeted=time.strftime("%Y-%m-%d %H:%M:%S"))
        mpath.write_text(json.dumps(m, indent=1))
    print(json.dumps({"retargeted_with_prompt": p.sha, "reader_check": check}, indent=1))
    if check["failures"]:
        sys.exit("some targets do not survive the product's reader: see manifest.json reader_check")


def summarize(recs: list[dict], args, seconds: float, check: dict) -> dict:
    def by(key, rows):
        return dict(sorted(Counter(key(r) for r in rows).items()))
    out = {"built": time.strftime("%Y-%m-%d %H:%M:%S"), "args": vars(args), "seconds": round(seconds, 1),
           "prompt_sha": recs[0]["prompt_sha"] if recs else None, "reader_check": check}
    for split in ("train", "dev"):
        rows = [r for r in recs if r["split"] == split]
        facts = [f for r in rows for f in json.loads(r["target"])["facts"]]
        out[split] = {
            "n": len(rows), "by_mode": by(lambda r: r["mode"], rows), "by_family": by(lambda r: r["family"], rows),
            "by_device": by(lambda r: r["device"], rows), "by_layout": by(lambda r: r["layout"], rows),
            "empty_targets": sum(not json.loads(r["target"])["facts"] for r in rows),
            "with_unreadable_reading": sum(any(not t["readable"] for t in r["truth"]) for r in rows),
            "facts_by_key": dict(sorted(Counter(f["key"] for f in facts).items())),
            "degradations": dict(Counter(d for r in rows for d in r["degradations"]).most_common()),
            "clean_photos": sum(not r["degradations"] for r in rows),
            "distinct_drugs": len({v for f in facts if f["key"] == "meds.list" for v in f["value"]}),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=3500, help="total examples (train + dev)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/vision_train/")
    ap.add_argument("--dev-frac", type=float, default=0.08)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--retarget", action="store_true", help="only rebuild prompts and targets from config")
    a = ap.parse_args()
    out = (ROOT / a.out).resolve() if not Path(a.out).is_absolute() else Path(a.out)
    from herald.config import get_settings
    index = get_settings().terminology_index
    if a.retarget:
        retarget(out, index)
        return
    if not index.exists():
        sys.exit(f"RxNorm index {index} is missing: build it with scripts/build_rxnorm_index.py (labels need it)")
    out.mkdir(parents=True, exist_ok=True)
    jobs = families.plan(a.n, a.dev_frac)
    t0 = time.time()
    with ProcessPoolExecutor(a.workers, initializer=_init_worker, initargs=(str(index),)) as pool:
        recs = list(pool.map(make_one, jobs, [a.seed] * len(jobs), [str(out)] * len(jobs), chunksize=8))
    check = ReaderCheck(index).run(recs)
    for split in ("train", "dev"):
        (out / f"{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                    for r in recs if r["split"] == split))
    manifest = summarize(recs, a, time.time() - t0, check)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: manifest[k] for k in ("seconds", "prompt_sha", "reader_check")}, indent=1))
    print(json.dumps({s: {k: manifest[s][k] for k in ("n", "by_mode", "empty_targets", "distinct_drugs")}
                      for s in ("train", "dev")}, indent=1))
    if check["failures"]:
        sys.exit("some targets do not survive the product's reader: see manifest.json reader_check")


if __name__ == "__main__":
    main()
