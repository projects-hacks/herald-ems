#!/usr/bin/env python3
"""Dev check for drug-name matching: eval/terminology/dev_names.yaml against the built index.

  python eval/terminology/dev_check.py                          # as configured
  python eval/terminology/dev_check.py --supplement-fuzzy none  # RxNav supplement names exact-only (all | active | none)

Reports, per list: how many resolve right, wrong (a different drug), or not at all, and every wrong one. The bar for
any matching change: 0 wrong on `never` (a non-drug becoming a drug), and no `resolve` name mapped to a wrong drug.
Tune here and on gold v1 only.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from herald.config import Settings, load_yaml  # noqa: E402
from herald.terminology import RxNormNormalizer  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--supplement-fuzzy", choices=["all", "active", "none"], default=None)
    a = ap.parse_args()
    names = yaml.safe_load((Path(__file__).parent / "dev_names.yaml").read_text())
    path = Settings.from_env().terminology_index
    d = json.loads(path.read_text())
    cfg = load_yaml("terminology.yaml")
    mode = a.supplement_fuzzy or cfg["rxnav"]["fuzzy"]
    fuzzy = {"all": d.get("supplement", {}), "active": d.get("supplement_active", []), "none": []}[mode]
    m = cfg["match"]
    n = RxNormNormalizer(d["ingredients"], d["names"], d["short"], d["multi"], heads=d.get("heads"),
                         supplement=d.get("supplement"), supplement_fuzzy=fuzzy, release=d["release"],
                         min_length=m["min_length"], fuzzy_min_ratio=m["fuzzy_min_ratio"],
                         phonetic_min_similarity=m["phonetic_min_similarity"], strength_units=m["strength_units"],
                         combination_separators=m["combination_separators"], contained_keys=cfg["keys"]["contained"])
    right = wrong = missed = 0
    wrongs = []
    for said, want in names["resolve"].items():
        r = n.normalize("meds.list", said)
        if not r.resolved:
            missed += 1
        elif r.value == want:
            right += 1
        else:
            wrong += 1
            wrongs.append(f"{said} -> {r.value} ({r.method}), expected {want}")
    became = []
    for said in names["never"]:
        for key in ("allergies", "meds.list"):
            r = n.normalize(key, said)
            if r.resolved:
                became.append(f"[{key}] {said} -> {r.value} ({r.method}, {r.score})")
    print(json.dumps({"supplement_fuzzy": mode, "resolve": {"right": right, "wrong": wrong, "missed": missed,
                                                             "n": len(names["resolve"])},
                      "never": {"became_a_drug": len(became), "n": len(names["never"]) * 2}}))
    for line in wrongs + became:
        print("  " + line)


if __name__ == "__main__":
    main()
