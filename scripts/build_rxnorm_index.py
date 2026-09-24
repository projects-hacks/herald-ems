#!/usr/bin/env python3
"""Build the local RxNorm index that herald/terminology/ matches drug names against.

  python scripts/build_rxnorm_index.py                  # download the pinned release, then build
  python scripts/build_rxnorm_index.py --zip path.zip   # build from a zip already on disk (sha256 still checked)
  python scripts/build_rxnorm_index.py --refresh-rxnav  # re-fetch the RxNav brand supplement instead of the cache

Source, release and checksum: config/terminology.yaml. Output: data/terminology/rxnorm_index.json (not in git).
- Every name (lowercase) of an ingredient (IN), precise ingredient (PIN), brand (BN), multi-ingredient (MIN),
  clinical or branded drug (SCD, SBD), prescribable name (PSN) or synonym (SY) maps to the ingredient(s) it contains.
- Product names: a branded product's name without its dose form, volume and strength, when a number is left
  ("tylenol #3 oral tablet" -> "tylenol 3"). Kept only when every product sharing it has the same ingredients.
- Supplement: brand names the prescribable subset leaves out (active but not prescribable, and retired), with their
  ingredients, from NLM's public RxNav API. Cached in data/terminology/rxnav_brands.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import threading
import time
import urllib.request
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from herald.config import load_yaml  # noqa: E402
from herald.terminology.rxnorm import strength_tail  # noqa: E402

NAME_TTYS = {"IN", "PIN", "BN", "MIN", "SCD", "SBD", "PSN", "SY"}
KINDS = ("IN", "PIN", "BN", "MIN", "SCDC", "SCD", "SBDC", "SBD")        # a concept's own type (SY/PSN are names)
SHORT_TYPES = {"IN", "PIN", "BN"}          # names eligible for fuzzy and phonetic matching
# Known mappings that must hold; a change in the file format or the build would otherwise pass silently.
EXPECT = {"jantoven": "warfarin", "warfarin sodium": "warfarin", "eliquis": "apixaban", "plavix": "clopidogrel",
          "lipitor": "atorvastatin", "percocet": "acetaminophen / oxycodone", "pradaxa": "dabigatran etexilate"}
EXPECT_HEADS = {"tylenol 3": "acetaminophen / codeine"}
EXPECT_SUPPLEMENT = {"coumadin": "warfarin", "zofran": "ondansetron", "vicodin": "acetaminophen / hydrocodone"}


def _norm(s: str) -> str:
    return " ".join(s.casefold().split())


# ---------- the release ----------
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_zip(path: Path) -> tuple[list[list[str]], list[list[str]], str]:
    with zipfile.ZipFile(path) as z:
        def rows(member):
            with z.open(member) as fh:
                return [line.split("|") for line in io.TextIOWrapper(fh, encoding="utf-8")]
        readme = next(n for n in z.namelist() if n.startswith("Readme"))
        first = z.read(readme).decode("utf-8", "replace").strip().splitlines()[0].strip()
        release = dt.datetime.strptime(first, "%B %d, %Y").date().isoformat()
        return rows("rrf/RXNCONSO.RRF"), rows("rrf/RXNREL.RRF"), release


# ---------- names -> ingredient sets ----------
def build(conso: list[list[str]], rel: list[list[str]], units: list[str]) -> dict:
    names: dict[str, set[str]] = defaultdict(set)           # rxcui -> names
    ttys: dict[str, set[str]] = defaultdict(set)            # rxcui -> TTYs of its names
    in_name: dict[str, str] = {}                             # ingredient rxcui -> its IN name
    dose_forms: set[str] = set()                             # RxNorm dose form and dose form group names
    for r in conso:
        rxcui, sab, tty, s, suppress = r[0], r[11], r[12], r[14], r[16]
        if sab != "RXNORM" or suppress != "N":
            continue
        ttys[rxcui].add(tty)
        if tty in NAME_TTYS:
            names[rxcui].add(_norm(s))
        if tty == "IN":
            in_name[rxcui] = _norm(s)
        if tty in ("DF", "DFG"):
            dose_forms.add(_norm(s))
    kind = {c: next((t for t in KINDS if t in ts), None) for c, ts in ttys.items()}

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
    head_keys: dict[str, set[str]] = defaultdict(set)
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
            if k == "SBD":
                h = product_head(n, dose_forms, units)
                if h:
                    head_keys[h].add(key)
    heads = {h: sorted(ks)[0] for h, ks in head_keys.items() if len(ks) == 1 and h not in index_names}
    return {"ingredients": ingredient_names, "multi": multi, "heads": dict(sorted(heads.items())),
            "names": {n: sorted(v) for n, v in sorted(index_names.items())}, "short": sorted(short)}


_BRACKET = re.compile(r"\s*\[[^\]]*\]\s*$")
_VOLUME = re.compile(r"^\d[\d.,]*\s*(?:ml|l|actuat|hr)\s+")


def product_head(name: str, dose_forms: set[str], units: list[str]) -> Optional[str]:
    """A branded product's name as people say it: no brand bracket, leading volume, dose form or trailing strength,
    and no "#". Only names that still carry a number are kept (the plain brand is already a name)."""
    s = _VOLUME.sub("", _BRACKET.sub("", name))
    for df in sorted(dose_forms, key=len, reverse=True):
        if s.endswith(" " + df):
            s = s[: -len(df) - 1]
            break
    s = strength_tail(s, units)
    s = " ".join(s.replace("#", " ").split())
    return s if re.search(r"\d", s) and re.search(r"[a-z]", s) else None


# ---------- RxNav brand supplement ----------
class RxNav:
    """NLM's public RxNav REST API, rate limited (config/terminology.yaml rxnav)."""

    def __init__(self, base: str, per_second: float):
        self.base, self.gap, self.lock, self.next = base.rstrip("/"), 1.0 / per_second, threading.Lock(), 0.0

    def get(self, path: str) -> dict:
        for attempt in range(4):
            with self.lock:
                wait = self.next - time.monotonic()
                self.next = max(self.next, time.monotonic()) + self.gap
            if wait > 0:
                time.sleep(wait)
            try:
                with urllib.request.urlopen(f"{self.base}/{path}", timeout=30) as r:
                    return json.loads(r.read())
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return {}

    def version(self) -> str:
        return str(self.get("version.json").get("version", "unknown"))

    def brands(self) -> list[dict]:
        active = self.get("allconcepts.json?tty=BN")["minConceptGroup"]["minConcept"]
        retired = [c for c in self.get("allstatus.json?status=Obsolete")["minConceptGroup"]["minConcept"]
                   if c.get("tty") == "BN"]
        return [{**c, "status": "active"} for c in active] + [{**c, "status": "obsolete"} for c in retired]

    def ingredients(self, brand: dict) -> list[str]:
        if brand["status"] == "active":
            groups = self.get(f"rxcui/{brand['rxcui']}/related.json?tty=IN")["relatedGroup"].get("conceptGroup") or []
            return sorted({p["rxcui"] for g in groups for p in g.get("conceptProperties") or []})
        hist = self.get(f"rxcui/{brand['rxcui']}/historystatus.json")["rxcuiStatusHistory"]
        return sorted({i["ingredientRxcui"] for i in (hist.get("derivedConcepts") or {}).get("ingredientConcept") or []})


def supplement(index: dict, cfg: dict, cache_path: Path, refresh: bool) -> tuple[dict, list[str], str]:
    """Brand names missing from the index -> their ingredient-set key; the ones that are active RxNorm brands (the
    rest are retired); the RxNav version they came from."""
    cache = json.loads(cache_path.read_text()) if cache_path.exists() and not refresh else {}
    api = RxNav(cfg["base"], cfg["requests_per_second"])
    if not cache.get("brands"):
        cache = {"version": api.version(), "fetched": dt.date.today().isoformat(), "brands": {}}
        brands = api.brands()
        todo = [b for b in brands if _norm(b["name"]) not in index["names"]]
        print(f"rxnav {cache['version']}: {len(brands)} brand names, {len(todo)} not in the subset; fetching "
              f"ingredients", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=6) as pool:
            for b, ing in zip(todo, pool.map(api.ingredients, todo)):
                cache["brands"][b["rxcui"]] = {"name": b["name"], "status": b["status"], "ingredients": ing}
        cache_path.write_text(json.dumps(cache, separators=(",", ":")))
    added, active = {}, set()
    for b in cache["brands"].values():
        n = _norm(b["name"])
        if n in index["names"] or not b["ingredients"] or not all(i in index["ingredients"] for i in b["ingredients"]):
            continue
        added[n] = "+".join(sorted(b["ingredients"], key=int))
        if b["status"] == "active":
            active.add(n)
    return dict(sorted(added.items())), sorted(active), cache["version"]


# ---------- checks ----------
def check(index: dict, anticoagulants: set[str]) -> list[str]:
    ing = index["ingredients"]

    def named(key):
        return " / ".join(sorted(ing[i] for i in key.split("+")))

    for table, expect in ((None, EXPECT), ("heads", EXPECT_HEADS), ("supplement", EXPECT_SUPPLEMENT)):
        for name, want in expect.items():
            if table is None:
                keys = index["names"].get(name)
                got = named(keys[0]) if keys and len(keys) == 1 else keys
            else:
                key = index[table].get(name)
                got = named(key) if key else None
            if got != want:
                raise SystemExit(f"sanity check failed: {name} -> {got}, expected {want}")
    return sorted(a for a in anticoagulants if a not in set(ing.values()))


def main() -> None:
    cfg = load_yaml("terminology.yaml")
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, help="a downloaded RxNorm_full_prescribe_*.zip (default: download it)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "terminology" / "rxnorm_index.json")
    ap.add_argument("--refresh-rxnav", action="store_true", help="re-fetch the brand supplement from RxNav")
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    src = a.zip
    if src is None:
        src = a.out.parent / Path(cfg["source"]["url"]).name
        if not src.exists():
            print(f"downloading {cfg['source']['url']} -> {src}", file=sys.stderr)
            urllib.request.urlretrieve(cfg["source"]["url"], src)
    digest = sha256(src)
    if digest != cfg["source"]["sha256"]:
        raise SystemExit(f"{src}: sha256 {digest} is not the pinned release ({cfg['source']['sha256']})")
    conso, rel, release = read_zip(src)
    if release != cfg["source"]["release"]:
        raise SystemExit(f"release {release} differs from config/terminology.yaml ({cfg['source']['release']})")
    index = build(conso, rel, cfg["match"]["strength_units"])
    index["supplement"], index["supplement_active"], rxnav_version = supplement(index, cfg["rxnav"], a.out.parent / "rxnav_brands.json",
                                                    a.refresh_rxnav)
    classes = [load_yaml(f) for f in cfg["classes"]]
    absent = check(index, {i for c in classes for g in c["groups"].values() for i in g["ingredients"]})
    index = {"release": release, "source": cfg["source"]["url"], "sha256": digest, "rxnav_version": rxnav_version,
             "built": dt.date.today().isoformat(),
             "counts": {k: len(index[k]) for k in ("ingredients", "names", "short", "multi", "heads", "supplement")},
             **index}
    a.out.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"release": release, "rxnav": rxnav_version, "out": str(a.out), **index["counts"],
                      "class_ingredients_not_in_release": absent}))


if __name__ == "__main__":
    main()
