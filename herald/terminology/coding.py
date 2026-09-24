"""Facts with drug or allergen values -> standard names with codes (the `FactCoder` interface).

Which keys hold drug names is content (config/terminology.yaml `keys`):
- list keys (`meds.list`, `allergies`): each item coded; an unmatched item stays as said, with a None code;
- record keys (`meds.given`): the drug field is coded, the rest of the record is untouched;
- class keys (`meds.anticoagulant`, from the class files in `classes`): coded; a drug outside the class (clopidogrel,
  an antiplatelet, said as the anticoagulant) is recorded as a medication instead, never under the class key.
A class drug is both a medication and the class fact, as the labeling guide labels it ("She's on Coumadin" ->
`meds.anticoagulant` warfarin and `meds.list` [warfarin]): either fact gives the other when it is missing.
An allergen RxNorm doesn't know may be a drug class ("sulfa"): it keeps its words and gets the NEMSIS ICD-10-CM code.
Anything not matched exactly waits for the medic's tap, with the reason (`provenance.hold_reason`, config `hold`).
What was said stays in `provenance.normalized` (and the utterance in `provenance.text`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from ..config import load_yaml
from ..core.ports import Normalizer
from ..core.schema import Coding, FactIn, NormalizedValue, Provenance, join_reasons
from ..core.vocabulary import Vocabulary
from .allergy import AllergyClasses


@dataclass(frozen=True)
class DrugClass:
    """A class of drugs that sets its own key (config/terminology/<class>.yaml)."""
    name: str
    key: str
    ingredients: frozenset[str]

    @classmethod
    def from_config(cls, rel: str) -> "DrugClass":
        d = load_yaml(rel)
        return cls(d["name"], d["key"], frozenset(i for g in d["groups"].values() for i in g["ingredients"]))

    def has(self, r: NormalizedValue) -> bool:
        return r.resolved and r.system == "rxnorm" and bool(self.ingredients & set(r.ingredients))


@dataclass
class _Coded:
    """One coded drug of a medication or class fact, kept to derive the other fact."""
    fact: FactIn
    result: NormalizedValue
    said: str
    provenance: Provenance            # the fact's provenance before coding (the guard's hold, the utterance)


class MedicationCoder:
    def __init__(self, normalizer: Normalizer, vocabulary: Vocabulary, *, classes: Iterable[DrugClass] = (),
                 lists: Iterable[str] = ("meds.list", "allergies"), records: Optional[Mapping[str, str]] = None,
                 meds_key: str = "meds.list", not_a_drug: Iterable[str] = ("", "none"),
                 systems: Optional[Mapping[str, str]] = None, holds: Optional[Mapping[str, str]] = None,
                 fallbacks: Optional[Mapping[str, Normalizer]] = None):
        self.normalizer, self.vocab = normalizer, vocabulary
        self.classes = {c.key: c for c in classes}
        self.lists, self.records, self.meds_key = set(lists), dict(records or {}), meds_key
        self.not_a_drug = {x.casefold() for x in not_a_drug}
        self.systems = dict(systems or {"rxnorm": "http://www.nlm.nih.gov/research/umls/rxnorm"})
        self.holds, self.fallbacks = dict(holds or {}), dict(fallbacks or {})

    @classmethod
    def from_config(cls, normalizer: Normalizer, vocabulary: Vocabulary) -> "MedicationCoder":
        cfg = load_yaml("terminology.yaml")
        keys = cfg["keys"]
        allergy = AllergyClasses.from_config(cfg["allergy_classes"], cfg["match"]["fuzzy_min_ratio"])
        return cls(normalizer, vocabulary, classes=[DrugClass.from_config(f) for f in cfg["classes"]],
                   lists=keys["lists"], records=keys["records"], meds_key=keys["meds"], not_a_drug=keys["not_a_drug"],
                   systems=cfg["systems"], holds=cfg["hold"], fallbacks={k: allergy for k in keys["allergy_classes"]})

    @property
    def release(self) -> str:
        return self.normalizer.release

    @property
    def keys(self) -> set[str]:
        return self.lists | set(self.records) | set(self.classes)

    # ---------- the FactCoder interface ----------
    def code(self, facts: list[FactIn]) -> list[FactIn]:
        out: list[FactIn] = []
        coded: list[_Coded] = []
        for f in facts:
            if f.key in self.lists:
                f, items = self._code_list(f)
                if f.key == self.meds_key:
                    coded += items
            elif f.key in self.records:
                f = self._code_record(f)
            elif f.key in self.classes:
                f, item = self._code_class_fact(f)
                if item is not None:
                    coded.append(item)
            out.append(f)
        return out + self._derive(out, coded)

    # ---------- one name ----------
    def _normalize(self, key: str, said: str) -> NormalizedValue:
        r = self.normalizer.normalize(key, said)
        if not r.resolved and key in self.fallbacks:
            other = self.fallbacks[key].normalize(key, said)
            if other.resolved:
                return other
        return r

    @staticmethod
    def _value(said: str, r: NormalizedValue) -> str:
        return r.value if r.resolved and r.system == "rxnorm" else said

    def _coding(self, r: NormalizedValue) -> Optional[Coding]:
        return Coding(system=self.systems[r.system], code=r.code) if r.resolved and r.code else None

    def _hold(self, said: str, r: NormalizedValue) -> Optional[str]:
        template = self.holds.get(r.method) if r.resolved else None
        shown = r.value if r.system == "rxnorm" else f"{r.ingredients[0]} ({r.code})"
        return template.format(said=said, value=shown) if template else None

    def _entry(self, said: str, r: NormalizedValue) -> dict:
        return {"said": said, "value": self._value(said, r), "system": self.systems.get(r.system) if r.resolved else None,
                "code": r.code if r.resolved else None, "method": r.method, "score": r.score}

    # ---------- per key kind ----------
    def _code_list(self, f: FactIn) -> tuple[FactIn, list[_Coded]]:
        try:
            items = self.vocab.coerce(f.key, f.value)
        except ValueError:
            return f, []
        if not items:
            return f, []
        values, codes, entries, holds, seen, results = [], [], [], [], set(), []
        for said in items:
            r = self._normalize(f.key, said)
            entries.append(self._entry(said, r))
            v = self._value(said, r)
            if v.casefold() in seen:          # "Coumadin" and "warfarin" in one list are one drug
                continue
            seen.add(v.casefold())
            values.append(v)
            codes.append(self._coding(r))
            holds.append(self._hold(said, r))
            results.append((said, r))
        prov = f.provenance.model_copy(update={"normalized": entries,
                                               "hold_reason": join_reasons(f.provenance.hold_reason, *holds)})
        coded = f.model_copy(update={"value": values, "code": codes, "provenance": prov})
        return coded, [_Coded(coded, r, said, f.provenance) for said, r in results]

    def _code_record(self, f: FactIn) -> FactIn:
        field = self.records[f.key]
        try:
            record = self.vocab.coerce(f.key, f.value)
        except ValueError:
            return f                                         # ingest rejects it with the reason
        said = str(record.get(field) or "").strip()
        if not said:
            return f
        r = self._normalize(f.key, said)
        prov = f.provenance.model_copy(update={"normalized": [self._entry(said, r)],
                                               "hold_reason": join_reasons(f.provenance.hold_reason, self._hold(said, r))})
        return f.model_copy(update={"value": {**record, field: self._value(said, r)}, "code": self._coding(r),
                                    "provenance": prov})

    def _code_class_fact(self, f: FactIn) -> tuple[FactIn, Optional[_Coded]]:
        said = str(f.value).strip()
        if said.casefold() in self.not_a_drug:
            return f, None
        r = self._normalize(f.key, said)
        prov = f.provenance.model_copy(update={"normalized": [self._entry(said, r)],
                                               "hold_reason": join_reasons(f.provenance.hold_reason, self._hold(said, r))})
        if not r.resolved:
            return f.model_copy(update={"code": None, "provenance": prov}), None
        if self.classes[f.key].has(r):
            coded = f.model_copy(update={"value": r.value, "code": self._coding(r), "provenance": prov})
        else:                                   # not in the class: a medication, never the class fact
            coded = f.model_copy(update={"key": self.meds_key, "value": [r.value], "code": [self._coding(r)],
                                         "provenance": prov})
        return coded, _Coded(coded, r, said, f.provenance)

    # ---------- a class drug is also a medication, and the other way round ----------
    def _derive(self, facts: list[FactIn], coded: list[_Coded]) -> list[FactIn]:
        have = {k: {str(f.value).casefold() for f in facts if f.key == k} for k in self.classes}
        meds = {str(x).casefold() for f in facts if f.key == self.meds_key and isinstance(f.value, list) for x in f.value}
        derived = []
        for c in coded:
            r, name = c.result, c.result.value.casefold()
            prov = c.provenance.model_copy(update={"normalized": [self._entry(c.said, r)],
                                                   "hold_reason": join_reasons(c.provenance.hold_reason,
                                                                               self._hold(c.said, r))})
            for cls in self.classes.values():
                if not cls.has(r):
                    continue
                if c.fact.key == self.meds_key and name not in have[cls.key]:
                    have[cls.key].add(name)
                    derived.append(c.fact.model_copy(update={"key": cls.key, "value": r.value,
                                                             "code": self._coding(r), "provenance": prov}))
                elif c.fact.key == cls.key and name not in meds:
                    meds.add(name)
                    derived.append(c.fact.model_copy(update={"key": self.meds_key, "value": [r.value],
                                                             "code": [self._coding(r)], "provenance": prov}))
        return derived
