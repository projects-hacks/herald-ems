"""Decontamination against the vision test set (eval/photos/gold.jsonl and its images). Read-only on eval/.

Two uses:
- at build time, `Exclusions` keeps the generator from printing a test label's (drug, strength) or showing a
  test photo's exact set of readings;
- after the build, `python scripts/vision_train/decontam.py --out data/vision_train` checks every record for
  collisions (same device type + same value set; same drug + strength; same printed drug line) and reports the
  perceptual-hash (DCT pHash, 64 bits) distance from every test image to its nearest training image."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image
from scipy.fft import dctn

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "eval/photos/gold.jsonl"

# gold `device` -> the training device types that are the same kind of object
DEVICE_KIND = {"bedside_monitor": "monitor", "defib_monitor": "monitor", "aed": "monitor", "capnograph": "monitor",
               "fingertip_oximeter": "oximeter", "bp_cuff": "bp_cuff", "bp_cuff_wrist": "bp_cuff", "glucometer": "glucometer",
               "thermometer": "thermometer", "smartwatch": "watch", "fitness_band": "watch", "phone_app": "phone",
               "pill_label": "label", "otc_bottle": "label", "stock_bottle": "label", "carton": "label", "blister": "label",
               "inhaler": "label", "pen": "label", "patch": "label", "med_list": "label", "med_list_handwritten": "label",
               "polst": "form", "dnr_order": "form", "existing": None}


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", s.lower())


def value_set(facts: Iterable) -> tuple:
    """Sorted (key, value) pairs; list values joined."""
    out = []
    for k, v in facts:
        out.append((k, "|".join(sorted(map(str, v))) if isinstance(v, list) else str(round(float(v), 1))
                    if isinstance(v, (int, float)) else str(v)))
    return tuple(sorted(out))


class Exclusions:
    def __init__(self, gold_path: Path = GOLD):
        self.rows = [json.loads(x) for x in open(gold_path)] if gold_path.exists() else []
        # readings are compared per kind of device (a watch showing HR 72 is not a test oximeter showing HR 72)
        self.value_sets = {(DEVICE_KIND.get(r.get("device"), r.get("device")), value_set(r["facts"]))
                           for r in self.rows if r["facts"] and r["mode"] == "monitor"}
        self.drug_strengths: set[tuple[str, str]] = set()
        self.label_lines: set[str] = set()
        for r in self.rows:
            meds = dict(r["facts"]).get("meds.list") if r["facts"] else None
            if meds and r.get("strength"):
                for m in meds:
                    self.drug_strengths.add((m, r["strength"]))
                for name in list(meds) + list((r.get("aliases") or {}).get("meds.list", [])):
                    self.label_lines.add(_norm_text(f"{name} {r['strength']}"))

    def monitor_collides(self, device: str, facts: Iterable) -> bool:
        """Same kind of device showing the same set of readings as a test photo (the `existing` test images have
        no device type, so they are matched against every kind)."""
        vs = value_set(facts)
        return (DEVICE_KIND.get(device, device), vs) in self.value_sets or (None, vs) in self.value_sets


# ---------- perceptual hash ----------
def phash(img: Image.Image) -> int:
    g = np.asarray(img.convert("L").resize((32, 32), Image.Resampling.LANCZOS), np.float32)
    c = dctn(g, norm="ortho")[:8, :8].flatten()
    bits = c[1:] > np.median(c[1:])
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming_min(qs: list[int], pool: np.ndarray) -> list[tuple[int, int]]:
    """For each query hash: (min distance, index of nearest) over pool (uint64 array)."""
    out = []
    for q in qs:
        x = np.bitwise_xor(pool, np.uint64(q))
        d = np.unpackbits(x.view(np.uint8).reshape(-1, 8), axis=1).sum(1)
        i = int(d.argmin())
        out.append((int(d[i]), i))
    return out


def check(out_dir: Path) -> dict:
    ex = Exclusions()
    recs = [json.loads(x) for s in ("train", "dev") for x in open(out_dir / f"{s}.jsonl")]
    gold_dev = {}
    for r in ex.rows:
        kind = DEVICE_KIND.get(r.get("device"), r.get("device"))
        if r["facts"] and r["mode"] == "monitor":
            gold_dev.setdefault((kind, value_set(r["facts"])), []).append(r["file"])
    value_hits, drug_hits, line_hits = [], [], []
    for rec in recs:
        facts = [(f["key"], f["value"]) for f in json.loads(rec["target"])["facts"]]
        kind = DEVICE_KIND.get(rec["device"], rec["device"])
        for k in (kind, None):
            if rec["mode"] == "monitor" and facts and (k, value_set(facts)) in gold_dev:
                value_hits.append((rec["id"], gold_dev[(k, value_set(facts))]))
        for f in json.loads(rec["target"])["facts"]:
            if f["key"] == "meds.list" and f.get("strength"):
                for m in f["value"]:
                    if any(m == g and _norm_text(f["strength"]) == _norm_text(s) for g, s in ex.drug_strengths):
                        drug_hits.append((rec["id"], m, f["strength"]))
        for t in rec.get("truth", []):
            if t["key"] == "meds.list" and _norm_text(t.get("shown", "")) in ex.label_lines:
                line_hits.append((rec["id"], t["shown"]))
    # perceptual hashes
    eval_imgs = sorted((ROOT / "eval/photos").glob("*.jpg"))
    eh = [phash(Image.open(p)) for p in eval_imgs]
    th = np.array([phash(Image.open(ROOT / r["image"])) for r in recs], dtype=np.uint64)
    near = hamming_min(eh, th)
    dists = [d for d, _ in near]
    # baseline: distance between training images of the SAME family (how close two different renders get)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(recs), size=min(300, len(recs)), replace=False)
    same = []
    for i in idx:
        fam = recs[i]["family"]
        others = [j for j in range(len(recs)) if recs[j]["family"] == fam and j != i]
        if others:
            pool = th[rng.choice(others, size=min(200, len(others)), replace=False)]
            same.append(hamming_min([int(th[i])], pool)[0][0])
    return {
        "records": len(recs), "gold_items": len(ex.rows), "eval_images": len(eval_imgs),
        "value_set_collisions": value_hits[:20], "n_value_set_collisions": len(value_hits),
        "drug_strength_collisions": drug_hits[:20], "n_drug_strength_collisions": len(drug_hits),
        "label_line_collisions": line_hits[:20], "n_label_line_collisions": len(line_hits),
        "phash_eval_to_nearest_train": {"min": min(dists), "p10": float(np.percentile(dists, 10)),
                                        "median": float(np.median(dists)), "max": max(dists),
                                        "n_le_6": sum(d <= 6 for d in dists), "n_le_10": sum(d <= 10 for d in dists)},
        "phash_nearest_per_eval_image": {p.name: {"dist": d, "nearest": recs[i]["id"]}
                                         for p, (d, i) in zip(eval_imgs, near)},
        "phash_train_same_family_nearest_baseline": {"median": float(np.median(same)) if same else None,
                                                     "p10": float(np.percentile(same, 10)) if same else None},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data/vision_train"))
    a = ap.parse_args()
    rep = check(Path(a.out))
    (Path(a.out) / "decontam_report.json").write_text(json.dumps(rep, indent=1))
    brief = {k: v for k, v in rep.items() if k != "phash_nearest_per_eval_image"}
    print(json.dumps(brief, indent=1))
    ok = not (rep["n_value_set_collisions"] or rep["n_drug_strength_collisions"] or rep["n_label_line_collisions"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
