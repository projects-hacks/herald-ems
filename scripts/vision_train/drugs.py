"""Real products to print on labels, read from the RxNorm index (public prescribable subset, data/terminology/).

A `Product` is one RxNorm clinical or branded drug with a single ingredient: the ingredient name (the target's
generic name, as the coder resolves it), the salt name as a generic label prints it ("metoprolol tartrate"), a
strength, a dose form and the brand names RxNorm lists for that product. Only products whose generic and brand
spellings resolve back to the same ingredient by an EXACT match are kept, so a target never depends on fuzzy
matching."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Optional

import yaml

CONTENT = Path(__file__).resolve().parent / "content"

_PRODUCT = re.compile(
    r"^(?:(?:[\d.]+ ml|\d+ actuat) )?(?:(?P<hr>\d+ hr) )?(?P<name>[a-z][a-z ,\-]*?) "
    r"(?P<num>\d+(?:\.\d+)?) (?P<unit>mg|mcg|unt/ml|mg/ml|meq|mg/actuat|mcg/actuat|mg/hr|mcg/hr|%) "
    r"(?P<form>[a-z \-]+?)(?: \[(?P<brand>[^\]]+)\])?$")
# allergen extracts, vaccines and diagnostics are in the prescribable subset but never in a medication bag
_NOT_A_HOME_MED = re.compile(r"extract|allergenic|pollen|venom|vaccine|antigen|toxoid|immune globulin|\bdander\b|mite")
UNIT_SHOW = {"mg": "mg", "mcg": "mcg", "unt/ml": "units/mL", "mg/ml": "mg/mL", "meq": "mEq", "mg/actuat": "mg",
             "mcg/actuat": "mcg", "mg/hr": "mg/hr", "mcg/hr": "mcg/hr", "%": "%"}


@dataclass
class Product:
    ingredient: str                   # RxNorm ingredient name: the target value
    code: str
    generic: str                      # as a generic label prints it (salt included)
    number: str                       # "0.5", "25", "100"
    unit: str                         # display unit ("mg", "units/mL")
    form: str                         # RxNorm dose form words
    package: str                      # bottle | inhaler | pen | patch
    brands: list[str] = field(default_factory=list)
    common: bool = False
    drug_class: str = "tail"

    @property
    def strength(self) -> str:
        """The canonical strength string the target carries ("5 mg", "100 units/mL")."""
        return f"{self.number} {self.unit}"


def _num(s: str) -> str:
    return s.rstrip("0").rstrip(".") if "." in s else s


def _display(num: str, unit: str, ingredient: str, package: str) -> tuple[str, str]:
    """Labels print micrograms for inhalers and levothyroxine (RxNorm writes 0.09 mg/actuat, 0.025 mg)."""
    shown = UNIT_SHOW[unit]
    small_mg = unit == "mg" and float(num) < 1
    if unit == "mg/actuat" or (small_mg and (ingredient == "levothyroxine" or package == "inhaler")):
        return _num(f"{float(num) * 1000:.3f}"), "mcg"
    if unit == "mg/hr" and float(num) < 1:                       # patches print 25 mcg/hr, not 0.025 mg/hr
        return _num(f"{float(num) * 1000:.1f}"), "mcg/hr"
    return _num(num), shown


class Catalog:
    """Products by ingredient; `pick` samples common classes most of the time and the long tail otherwise."""

    def __init__(self, products: list[Product], tail_share: float):
        self.by_ing: dict[str, list[Product]] = defaultdict(list)
        for p in products:
            self.by_ing[p.ingredient].append(p)
        self.common = sorted(i for i, ps in self.by_ing.items() if any(p.common for p in ps))
        self.tail = sorted(i for i in self.by_ing if i not in set(self.common))
        self.tail_share = tail_share
        self.excluded: set[tuple[str, str]] = set()

    def exclude(self, pairs: set[tuple[str, str]]) -> None:
        """(ingredient, strength) pairs never printed (decontamination against the test labels)."""
        self.excluded |= {(i.lower(), re.sub(r"\s+", "", s.lower())) for i, s in pairs}

    def _allowed(self, p: Product) -> bool:
        return (p.ingredient, re.sub(r"\s+", "", p.strength.lower())) not in self.excluded

    def pick(self, rng: Random, package: Optional[str] = None) -> Product:
        for _ in range(200):
            pool = self.tail if (rng.random() < self.tail_share and self.tail) else self.common
            ing = rng.choice(pool)
            cands = [p for p in self.by_ing[ing] if self._allowed(p) and (package is None or p.package == package)]
            if cands:
                return rng.choice(cands)
        raise RuntimeError(f"no product for package {package}")

    def __len__(self) -> int:
        return sum(len(v) for v in self.by_ing.values())


def build_catalog(index_path: Path, normalizer) -> Catalog:
    """Parse the index's product names into Products; keep exact-resolving ones only."""
    cfg = yaml.safe_load((CONTENT / "drugs.yaml").read_text())
    common = {name: cls for cls, names in cfg["common"].items() for name in names}
    form_pkg = {f: pkg for pkg, forms in cfg["forms"].items() for f in forms}
    d = json.loads(Path(index_path).read_text())
    ingredients, names = d["ingredients"], d["names"]
    products: dict[tuple, Product] = {}
    brands: dict[tuple, set] = defaultdict(set)
    ok_cache: dict[tuple[str, str], bool] = {}

    def exact(said: str, code: str) -> bool:
        k = (said, code)
        if k not in ok_cache:
            r = normalizer.normalize("meds.list", said)
            ok_cache[k] = r.method == "exact" and r.code == code
        return ok_cache[k]

    parsed = [(m, codes[0]) for nm, codes in names.items()
              if len(codes) == 1 and "+" not in codes[0] and (m := _PRODUCT.match(nm)) and m["form"] in form_pkg]
    brand_names = {m["brand"] for m, _ in parsed if m["brand"]}
    for m, code in parsed:
        ing = ingredients.get(code)
        if not ing or m["name"] in brand_names:
            continue                                   # a brand-named product line; brands come from [brackets]
        if ing not in common and (len(ing) > 28 or _NOT_A_HOME_MED.search(ing) or any(ch.isdigit() for ch in ing)):
            continue
        num, unit = _display(m["num"], m["unit"], ing, form_pkg[m["form"]])
        key = (ing, m["name"], num, unit, m["form"])
        if key not in products:
            if not (exact(ing, code) and exact(m["name"], code)):
                continue
            products[key] = Product(ing, code, m["name"], num, unit, m["form"], form_pkg[m["form"]],
                                    common=ing in common, drug_class=common.get(ing, "tail"))
        if m["brand"] and exact(m["brand"], code):
            brands[key].add(m["brand"])
    for key, p in products.items():
        p.brands = sorted(brands.get(key, ()))
    return Catalog(list(products.values()), cfg["tail_share"])


def load_normalizer(index_path: Path):
    from herald.terminology.rxnorm import RxNormNormalizer
    return RxNormNormalizer.load(index_path)
