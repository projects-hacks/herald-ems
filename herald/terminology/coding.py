"""Facts with drug or allergen values -> standard generic names with RxNorm codes (the `FactCoder` interface).

- `meds.list` and `allergies`: each item normalized; unmatched items stay as said, with a None code.
- `meds.anticoagulant`: normalized; a drug outside the anticoagulant class (config/terminology/anticoagulants.yaml,
  e.g. clopidogrel, an antiplatelet) is recorded as a medication instead, never as an anticoagulant.
- An anticoagulant is both a medication and the anticoagulant, as the labeling guide labels it ("She's on Coumadin"
  -> `meds.anticoagulant` warfarin and `meds.list` [warfarin]): either fact gives the other when it is missing.
What was said stays in `provenance.normalized` (and the utterance in `provenance.text`).
"""
from __future__ import annotations

from typing import Iterable

from ..config import load_yaml
from ..core.ports import Normalizer
from ..core.schema import FactIn, NormalizedValue
from ..core.vocabulary import Vocabulary

_NOT_A_DRUG = ("", "none")


def anticoagulant_class() -> set[str]:
    return {i for c in load_yaml("terminology/anticoagulants.yaml")["classes"].values() for i in c["ingredients"]}


def _entry(said: str, r: NormalizedValue) -> dict:
    return {"said": said, "value": r.value, "code": r.code, "method": r.method, "score": r.score}


class MedicationCoder:
    def __init__(self, normalizer: Normalizer, anticoagulants: Iterable[str], vocabulary: Vocabulary,
                 list_keys: Iterable[str] = ("meds.list", "allergies"),
                 anticoagulant_key: str = "meds.anticoagulant", meds_key: str = "meds.list"):
        self.normalizer, self.vocab = normalizer, vocabulary
        self.anticoagulants = frozenset(anticoagulants)
        self.list_keys, self.anticoagulant_key, self.meds_key = set(list_keys), anticoagulant_key, meds_key

    @classmethod
    def from_config(cls, normalizer: Normalizer, vocabulary: Vocabulary) -> "MedicationCoder":
        keys = load_yaml("terminology.yaml")["keys"]
        return cls(normalizer, anticoagulant_class(), vocabulary, keys["list"], keys["anticoagulant"])

    @property
    def release(self) -> str:
        return self.normalizer.release

    def anticoagulant_names(self) -> dict[str, str]:
        """Every generic and brand name of an anticoagulant -> its ingredient (for the rules fallback)."""
        return self.normalizer.names_for(self.anticoagulants)

    def is_anticoagulant(self, r: NormalizedValue) -> bool:
        return r.resolved and bool(self.anticoagulants & set(r.ingredients))

    def code(self, facts: list[FactIn]) -> list[FactIn]:
        out: list[FactIn] = []
        coded: list[tuple[FactIn, NormalizedValue]] = []      # coded meds.list items and anticoagulants
        for f in facts:
            if f.key in self.list_keys:
                f, results = self._code_list(f)
                if f.key == self.meds_key:
                    coded += [(f, r) for r in results]
            elif f.key == self.anticoagulant_key:
                f, r = self._code_anticoagulant(f)
                if r is not None:
                    coded.append((f, r))
            out.append(f)
        return out + self._derive(out, coded)

    def _code_list(self, f: FactIn) -> tuple[FactIn, list[NormalizedValue]]:
        try:
            items = self.vocab.coerce(f.key, f.value)
        except ValueError:
            return f, []
        if not items:
            return f, []
        values, codes, results, entries, seen = [], [], [], [], set()
        for said in items:
            r = self.normalizer.normalize(f.key, said)
            entries.append(_entry(said, r))
            v = r.value if r.resolved else said
            if v.casefold() in seen:          # "Coumadin" and "warfarin" in one list are one drug
                continue
            seen.add(v.casefold())
            values.append(v)
            codes.append(r.code if r.resolved else None)
            results.append(r)
        prov = f.provenance.model_copy(update={"normalized": entries})
        return f.model_copy(update={"value": values, "code": codes, "provenance": prov}), results

    def _code_anticoagulant(self, f: FactIn) -> tuple[FactIn, NormalizedValue | None]:
        said = str(f.value).strip()
        if said.casefold() in _NOT_A_DRUG:
            return f, None
        r = self.normalizer.normalize(f.key, said)
        prov = f.provenance.model_copy(update={"normalized": [_entry(said, r)]})
        if not r.resolved:
            return f.model_copy(update={"code": None, "provenance": prov}), r
        if self.is_anticoagulant(r):
            return f.model_copy(update={"value": r.value, "code": r.code, "provenance": prov}), r
        return f.model_copy(update={"key": self.meds_key, "value": [r.value], "code": [r.code], "provenance": prov}), r

    def _derive(self, facts: list[FactIn], coded: list[tuple[FactIn, NormalizedValue]]) -> list[FactIn]:
        anticoagulants = {str(f.value).casefold() for f in facts if f.key == self.anticoagulant_key}
        meds = {str(x).casefold() for f in facts if f.key == self.meds_key and isinstance(f.value, list)
                for x in f.value}
        derived = []
        for f, r in coded:
            if not self.is_anticoagulant(r):
                continue
            said = next((e["said"] for e in f.provenance.normalized or [] if e["value"] == r.value), r.value)
            prov = f.provenance.model_copy(update={"normalized": [_entry(said, r)]})
            if f.key == self.meds_key and r.value.casefold() not in anticoagulants:
                anticoagulants.add(r.value.casefold())
                derived.append(f.model_copy(update={"key": self.anticoagulant_key, "value": r.value, "code": r.code,
                                                    "provenance": prov}))
            elif f.key == self.anticoagulant_key and r.value.casefold() not in meds:
                meds.add(r.value.casefold())
                derived.append(f.model_copy(update={"key": self.meds_key, "value": [r.value], "code": [r.code],
                                                    "provenance": prov}))
        return derived
