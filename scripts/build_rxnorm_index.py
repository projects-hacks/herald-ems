#!/usr/bin/env python3
"""Build the local RxNorm index that herald/terminology/ matches drug names against.

  python scripts/build_rxnorm_index.py                  # download the current release, then build
  python scripts/build_rxnorm_index.py --zip path.zip   # build from a zip already on disk

Source and release: config/terminology.yaml. Output: data/terminology/rxnorm_index.json (not in git).
Every name (lowercase) of an ingredient (IN), precise ingredient (PIN), brand (BN), multi-ingredient (MIN),
clinical or branded drug (SCD, SBD), prescribable name (PSN) or synonym (SY) maps to the ingredient(s) it contains.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from herald.config import load_yaml  # noqa: E402

NAME_TTYS = {"IN", "PIN", "BN", "MIN", "SCD", "SBD", "PSN", "SY"}
CONCEPT_TTYS = {"IN", "PIN", "BN", "MIN", "SCDC", "SCD", "SBDC", "SBD"}   # a concept's own type (SY/PSN are names)
SHORT_TYPES = {"IN", "PIN", "BN"}          # names eligible for fuzzy and phonetic matching
EXPECT = {"jantoven": "warfarin", "warfarin sodium": "warfarin", "eliquis": "apixaban", "plavix": "clopidogrel",
          "lipitor": "atorvastatin", "percocet": "acetaminophen / oxycodone", "coumadin": "warfarin",
          "pradaxa": "dabigatran etexilate"}


def read_zip(path: Path) -> tuple[list[list[str]], list[list[str]], str]:
    with zipfile.ZipFile(path) as z:
        def rows(member):
            with z.open(member) as fh:
                return [line.split("|") for line in io.TextIOWrapper(fh, encoding="utf-8")]
        readme = next(n for n in z.namelist() if n.startswith("Readme"))
        first = z.read(readme).decode("utf-8", "replace").strip().splitlines()[0].strip()
        release = dt.datetime.strptime(first, "%B %d, %Y").date().isoformat()
        return rows("rrf/RXNCONSO.RRF"), rows("rrf/RXNREL.RRF"), release


def build(conso: list[list[str]], rel: list[list[str]], supplement: list[dict]) -> dict:
    names: dict[str, set[str]] = defaultdict(set)           # rxcui -> names
    ttys: dict[str, set[str]] = defaultdict(set)            # rxcui -> TTYs of its names
    in_name: dict[str, str] = {}                             # ingredient rxcui -> its IN name
    for r in conso:
        rxcui, sab, tty, s, suppress = r[0], r[11], r[12], r[14], r[16]
        if sab != "RXNORM" or suppress != "N":
            continue
        ttys[rxcui].add(tty)
        if tty in NAME_TTYS:
            names[rxcui].add(" ".join(s.casefold().split()))
        if tty == "IN":
            in_name[rxcui] = " ".join(s.casefold().split())
    kind = {c: next((t for t in ("IN", "PIN", "BN", "MIN", "SCDC", "SCD", "SBDC", "SBD") if t in ts), None)
            for c, ts in ttys.items()}

    # RXNREL reads "RXCUI2 <RELA> RXCUI1": (warfarin, Jantoven, tradename_of) = Jantoven is a tradename of warfarin.
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in rel:
        if r[10] == "RXNORM" and r[7]:
            out[r[4]][r[7]].add(r[0])

    ingredient_names = {c: in_name[c] for c, k in kind.items() if k == "IN"}
    memo: dict[str, frozenset] = {}

    def ingredients(c: str, depth: int = 0) -> frozenset:
        if c in memo:
            return memo[c]
        k, e = kind.get(c), out.get(c, {})
        if depth > 4 or k is None:
            got: set[str] = set()
        elif k == "IN":
            got = {c}
        elif k == "PIN":
            got = {t for t in e.get("form_of", ()) if kind.get(t) == "IN"}
        elif k in ("BN", "MIN"):
            got = {t for t in e.get("tradename_of", set()) | e.get("has_part", set()) if kind.get(t) == "IN"}
        elif k == "SCDC":
            got = {t for t in e.get("has_ingredient", ()) if kind.get(t) == "IN"}
            got |= {i for p in e.get("has_precise_ingredient", ()) for i in ingredients(p, depth + 1)}
        elif k == "SCD":
            got = {i for p in e.get("consists_of", ()) for i in ingredients(p, depth + 1)}
        else:                                # SBD, SBDC: via the generic drug they are a tradename of
            got = {i for p in e.get("tradename_of", ()) for i in ingredients(p, depth + 1)}
        memo[c] = frozenset(got)
        return memo[c]

    index_names: dict[str, set[str]] = defaultdict(set)     # name -> ingredient-set keys ("11289", "161+7804")
    short: set[str] = set()
    multi: dict[str, str] = {}
    for c, k in kind.items():
        ing = ingredients(c)
        if not ing:
            continue
        key = "+".join(sorted(ing, key=int))
        if k == "MIN":
            multi[key] = c
        for n in names[c]:
            index_names[n].add(key)
            if k in SHORT_TYPES:
                short.add(n)
    for s in supplement:
        missing = [i for i in s["ingredients"] if i not in ingredient_names]
        if missing:
            raise SystemExit(f"supplement {s['name']}: ingredient(s) {missing} not in this RxNorm release")
        n = " ".join(s["name"].casefold().split())
        index_names[n].add("+".join(sorted(s["ingredients"], key=int)))
        if s["tty"] in SHORT_TYPES:
            short.add(n)
    return {"ingredients": ingredient_names, "multi": multi,
            "names": {n: sorted(v) for n, v in sorted(index_names.items())}, "short": sorted(short)}


def check(index: dict, anticoagulants: set[str]) -> list[str]:
    """Known mappings must hold; a change in the file format would otherwise pass silently."""
    ing = index["ingredients"]
    for name, want in EXPECT.items():
        keys = index["names"].get(name)
        got = " / ".join(sorted(ing[i] for i in keys[0].split("+"))) if keys and len(keys) == 1 else keys
        if got != want:
            raise SystemExit(f"sanity check failed: {name} -> {got}, expected {want}")
    present = set(ing.values())
    return sorted(a for a in anticoagulants if a not in present)


def main() -> None:
    cfg = load_yaml("terminology.yaml")
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, help="a downloaded RxNorm_full_prescribe_*.zip (default: download it)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "terminology" / "rxnorm_index.json")
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    src = a.zip
    if src is None:
        src = a.out.parent / "RxNorm_full_prescribe_current.zip"
        print(f"downloading {cfg['source']['url']} -> {src}")
        urllib.request.urlretrieve(cfg["source"]["url"], src)
    conso, rel, release = read_zip(src)
    index = build(conso, rel, load_yaml("terminology/supplement.yaml")["names"])
    classes = load_yaml("terminology/anticoagulants.yaml")["classes"]
    absent = check(index, {i for c in classes.values() for i in c["ingredients"]})
    index = {"release": release, "source": cfg["source"]["url"], "built": dt.date.today().isoformat(),
             "counts": {"ingredients": len(index["ingredients"]), "names": len(index["names"]),
                        "short": len(index["short"]), "multi": len(index["multi"])}, **index}
    a.out.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"release": release, "out": str(a.out), **index["counts"],
                      "anticoagulants_not_in_release": absent}))
    if release != cfg["source"]["release"]:
        print(f"note: release {release} differs from config/terminology.yaml ({cfg['source']['release']}); "
              "update it there in the same PR", file=sys.stderr)


if __name__ == "__main__":
    main()
