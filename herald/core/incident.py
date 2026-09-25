"""The incident: an append-only store of facts with their confirmation status.

Facts in; queries out. The patient picture (checklists, scores, alerts, clocks) is computed from this store by
core/snapshot.py's Projector, which is injected, so this class knows nothing about scores or screens.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from .confirmation import ConfirmationPolicy
from .schema import Fact, FactIn, Status, new_id, utcnow
from .vocabulary import Vocabulary, default_vocabulary, norm_value


class Incident:
    def __init__(self, dispatch: Optional[str] = None, *, vocabulary: Optional[Vocabulary] = None,
                 policy: Optional[ConfirmationPolicy] = None, projector=None):
        self.id = new_id("inc")
        self.patient_label: Optional[str] = None
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
        self.audit_log: list[dict] = []
        self.ended_at = None
        self.media_ids: dict[str, set[str]] = {"audio": set(), "photo": set()}
        self.media_disposal: Optional[dict] = None
        self.news2_history: list[dict] = []   # score history, recorded once per utterance by the projector
        self.ed_sync: dict[str, dict] = {}
        self.lock = threading.RLock()

    # ---------- ingest ----------
    def ensure_open(self) -> None:
        if self.ended_at is not None:
            raise IncidentEnded("this incident has ended; start a new incident before capturing more data")

    def register_media(self, kind: str, media_id: str) -> None:
        """Attach generated evidence to this call while holding the same lock used to end it."""
        with self.lock:
            self.ensure_open()
            self.media_ids[kind].add(media_id)

    def validate(self, fin: FactIn) -> Any:
        """Raise ValueError if `ingest` would reject this fact (lets a batch be all-or-nothing)."""
        return self.vocab.validate(fin.key, fin.value)

    def ingest(self, fin: FactIn, record: bool = True) -> Fact:
        value = self.validate(fin)
        with self.lock:
            self.ensure_open()
            prev = self.latest(fin.key)
            data = fin.model_dump()
            data["value"] = value
            fact = Fact(**data, id=new_id("f"), ts=utcnow(), status=self.policy.initial_status(fin, prev, value),
                        previous_value=prev.value if prev else None, previous_ts=prev.ts if prev else None)
            self.facts.append(fact)
            if record:
                self.commit()
            return fact

    def set_status(self, fact_id: str, status: Status, actor: str = "medic") -> Fact:
        with self.lock:
            self.ensure_open()
            for f in self.facts:
                if f.id == fact_id:
                    previous = f.status
                    f.status = status
                    if previous != status:
                        self.audit_log.append({
                            "at": utcnow().isoformat(), "action": "fact_status_changed", "actor": actor,
                            "fact_id": f.id, "key": f.key, "from": previous.value, "to": status.value,
                        })
                    self.commit()
                    return f
        raise KeyError(fact_id)

    def commit(self) -> None:
        """Call after one utterance's facts are ingested, so score history is recorded once per utterance."""
        with self.lock:
            self.projector.record_scores(self)

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
            if meta.get("merge") == "each":             # every fact is its own event (a dose given, a procedure)
                seen, events = set(), []
                for f in h:
                    if norm_value(f.value) not in seen:
                        seen.add(norm_value(f.value))
                        events.append(f.value)
                out[key] = events
            elif meta.get("merge") == "accumulate":
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


class IncidentEnded(RuntimeError):
    """A write was attempted after the crew ended the call."""
