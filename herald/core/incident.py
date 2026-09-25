"""The incident: an append-only store of facts with their confirmation status.

Facts in; queries out. The patient picture (checklists, scores, alerts, clocks) is computed from this store by
core/snapshot.py's Projector, which is injected, so this class knows nothing about scores or screens.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from .confirmation import ConfirmationPolicy
from .schema import CapturedBy, Fact, FactIn, Provenance, Role, Status, new_id, utcnow
from .vocabulary import Vocabulary, default_vocabulary, norm_value


class Incident:
    def __init__(self, dispatch: Optional[str] = None, *, vocabulary: Optional[Vocabulary] = None,
                 policy: Optional[ConfirmationPolicy] = None, projector=None):
        self.id = new_id("inc")
        self.dispatch = dispatch
        self.started = utcnow()
        self.vocab = vocabulary or default_vocabulary()
        self.policy = policy or ConfirmationPolicy(self.vocab)
        if projector is None:
            from .snapshot import default_projector
            projector = default_projector()
        self.projector = projector
        self.facts: list[Fact] = []
        self.transcripts: list[dict] = []
        self.news2_history: list[dict] = []   # score history, recorded once per utterance by the projector
        self.ed_sync: dict[str, dict] = {}
        self.lock = threading.RLock()

    # ---------- ingest ----------
    def validate(self, fin: FactIn) -> Any:
        """Raise ValueError if `ingest` would reject this fact (lets a batch be all-or-nothing)."""
        return self.vocab.validate(fin.key, fin.value)

    def ingest(self, fin: FactIn, record: bool = True) -> Fact:
        value = self.validate(fin)
        with self.lock:
            prev = self.latest(fin.key)
            data = fin.model_dump()
            data["value"] = value
            fact = Fact(**data, id=new_id("f"), ts=utcnow(), status=self.policy.initial_status(fin, prev, value),
                        previous_value=prev.value if prev else None, previous_ts=prev.ts if prev else None)
            self.facts.append(fact)
            if record:
                self.commit()
            return fact

    def set_status(self, fact_id: str, status: Status) -> Fact:
        with self.lock:
            for f in self.facts:
                if f.id == fact_id:
                    f.status = status
                    self.commit()
                    return f
        raise KeyError(fact_id)

    def commit(self) -> None:
        """Call after one utterance's facts are ingested, so score history is recorded once per utterance."""
        with self.lock:
            self.projector.record_scores(self)

    def correct(self, fact_id: str, value: Any) -> Fact:
        """An explicit medic correction replaces only the current fact, retaining its evidence."""
        with self.lock:
            old = next((fact for fact in self.facts if fact.id == fact_id), None)
            if old is None:
                raise KeyError(fact_id)
            if self.latest(old.key) is not old:
                raise RuntimeError("This field changed. Review its current value before correcting it.")
            kind = self.vocab.meta(old.key)["type"]
            valid_type = (
                isinstance(value, bool) if kind == "bool" else
                isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value) if kind == "list" else
                isinstance(value, (int, float)) and not isinstance(value, bool) if kind in ("int", "float") else
                isinstance(value, str) and bool(value.strip())
            )
            if value is None or not valid_type:
                raise ValueError(f"Enter a valid {kind} value for {self.vocab.label(old.key)}")
            if kind == "int" and value != int(value):
                raise ValueError("Enter a whole number")
            fin = FactIn(key=old.key, value=value, unit=old.unit, role=Role.medic, speaker="medic correction",
                         captured_by=CapturedBy.medic, confidence=1.0,
                         provenance=Provenance(text=f"manual correction of {fact_id}", extractor="manual-correction"))
            self.validate(fin)  # validate before changing either record
            corrected = self.ingest(fin, record=False)
            old.status = Status.rejected
            corrected.status = Status.confirmed
            self.commit()
            return corrected

    # ---------- queries ----------
    def history(self, key: str, confirmed_only: bool = False) -> list[Fact]:
        return [f for f in self.facts if f.key == key and f.status != Status.rejected
                and (not confirmed_only or f.status == Status.confirmed)]

    def latest(self, key: str, confirmed_only: bool = False) -> Optional[Fact]:
        h = self.history(key, confirmed_only)
        return h[-1] if h else None

    def values(self, confirmed_only: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, meta in self.vocab.keys.items():
            h = self.history(key, confirmed_only)
            if not h:
                continue
            if meta.get("merge") == "accumulate":
                seen, merged = set(), []
                for f in h:
                    for x in (f.value or []):
                        if norm_value(x) not in seen:
                            seen.add(norm_value(x))
                            merged.append(x)
                out[key] = merged
            else:
                out[key] = h[-1].value
        return out

    def snapshot(self) -> dict:
        return self.projector.snapshot(self)
