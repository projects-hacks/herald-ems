"""Which readings may be confirmed as a set, and which need the medic's eye one at a time.

One camera read of the patient monitor produces HR, BP, SpO2 and RR at once, and every one of them is born
unconfirmed. Confirming a whole frame's readings in one action is what makes monitor-watch usable; confirming a
reading that JUMPED in the same sweep is what would make it dangerous. This module decides between the two.

It decides taps, never meaning. The rules and the wording are content (config/corroboration.yaml); this module is the
engine. There is deliberately no confidence gate for camera facts: see the note at the top of that file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..config import load_yaml
from .schema import Fact, Status
from .vocabulary import Vocabulary


@dataclass(frozen=True)
class Decision:
    """One reading's verdict inside a capture group."""
    fact_id: str
    key: str
    label: str
    batchable: bool
    reason: Optional[str] = None      # why it is not batchable, in the medic's words (from config)

    def as_row(self) -> dict:
        return {"id": self.fact_id, "key": self.key, "label": self.label, "reason": self.reason}


def _matches(key: str, patterns) -> bool:
    return any(key.startswith(p) if p.endswith(".") else key == p for p in patterns)


class CorroborationRules:
    """config/corroboration.yaml as an engine: risk tier, plausible step, and the wording for each verdict."""

    def __init__(self, c: dict):
        tiers = c["tiers"]
        self.batched_keys = list(tiers["batched"]["keys"])
        self.batched_sources = frozenset(tiers["batched"]["sources"])
        self.individual_keys = list(tiers["individual"]["keys"])
        self.first_reading = str(c["first_reading"])
        self.steps: dict[str, dict] = dict(c["plausible_step"])
        self.wording: dict[str, str] = dict(c["reasons"])

    @classmethod
    def from_config(cls, rel: str = "corroboration.yaml") -> "CorroborationRules":
        return cls(load_yaml(rel))

    def problems(self, vocab: Vocabulary) -> list[str]:
        """Content checks, so a typo in the config fails loudly instead of quietly widening a batch."""
        out = []
        for key in self.steps:
            if key not in vocab.keys:
                out.append(f"corroboration.yaml: plausible_step key {key} is not in the vocabulary")
            elif not isinstance(self.steps[key].get("max_step"), (int, float)):
                out.append(f"corroboration.yaml: plausible_step {key} needs a numeric max_step")
        for pattern in self.batched_keys + self.individual_keys:
            if not pattern.endswith(".") and pattern not in vocab.keys:
                out.append(f"corroboration.yaml: {pattern} is not a vocabulary key or a key prefix")
        if self.first_reading not in ("batch", "individual"):
            out.append("corroboration.yaml: first_reading must be batch or individual")
        overlap = [p for p in self.batched_keys if _matches(p, self.individual_keys)]
        if overlap:
            out.append(f"corroboration.yaml: {overlap} is both batched and individual")
        return out

    def says(self, name: str, **fields: Any) -> str:
        return self.wording[name].format(**fields)

    # ---------- tiering ----------
    def always_individual(self, key: str) -> bool:
        return _matches(key, self.individual_keys)

    def batchable_key(self, key: str) -> bool:
        return _matches(key, self.batched_keys) and not self.always_individual(key)

    def batchable_source(self, captured_by: str) -> bool:
        return captured_by in self.batched_sources

    # ---------- corroboration ----------
    def step_limit(self, key: str) -> Optional[float]:
        rule = self.steps.get(key)
        return None if rule is None else float(rule["max_step"])

    def within_step(self, key: str, previous: Any, value: Any) -> Optional[bool]:
        """True when the move is routine, False when it is a jump, None when the rule cannot be applied."""
        limit = self.step_limit(key)
        if limit is None or isinstance(previous, bool) or isinstance(value, bool):
            return None
        if not isinstance(previous, (int, float)) or not isinstance(value, (int, float)):
            return None
        return abs(value - previous) <= limit


class BatchConfirmation:
    """Capture groups: the unconfirmed readings of one frame, split into a one-tap set and the ones to look at."""

    def __init__(self, vocabulary: Vocabulary, rules: CorroborationRules):
        self.vocab, self.rules = vocabulary, rules

    # ---------- grouping ----------
    def frame_ids(self, inc) -> list[str]:
        """Frames that still have an unconfirmed reading, oldest first (provenance.frame_id, stamped by the reader)."""
        seen: dict[str, None] = {}
        for f in inc.facts:
            if f.status == Status.unconfirmed and f.provenance.frame_id:
                seen.setdefault(f.provenance.frame_id, None)
        return list(seen)

    def group(self, inc, frame_id: str) -> list[Fact]:
        return [f for f in inc.facts
                if f.status == Status.unconfirmed and f.provenance.frame_id == frame_id]

    # ---------- deciding ----------
    def decide(self, fact: Fact) -> Decision:
        label = self.vocab.label(fact.key)
        verdict = lambda ok, name=None, **kw: Decision(fact.id, fact.key, label, ok,
                                                       None if name is None else self.rules.says(name, **kw))
        if fact.provenance.hold_reason:
            return verdict(False, "held")
        if fact.verify and fact.verify.status == "mismatch" and not fact.verify.resolution:
            return verdict(False, "mismatch")
        if fact.key in self.vocab.contradiction_keys and fact.previous_value is not None:
            return verdict(False, "contradiction")
        if self.rules.always_individual(fact.key) or self.vocab.meta(fact.key).get("require_tap"):
            return verdict(False, "tier", label=label)
        if not self.rules.batchable_key(fact.key):
            return verdict(False, "tier", label=label)
        if not self.rules.batchable_source(fact.captured_by.value):
            return verdict(False, "source")
        if fact.previous_value is None:
            return verdict(True) if self.rules.first_reading == "batch" else verdict(False, "first", label=label)
        within = self.rules.within_step(fact.key, fact.previous_value, fact.value)
        if within is None:
            return verdict(False, "no_rule", label=label)
        if within:
            return verdict(True)
        return verdict(False, "jump", label=label, previous=fact.previous_value,
                       delta=abs(fact.value - fact.previous_value), limit=self.rules.step_limit(fact.key))

    def review(self, facts: list[Fact]) -> list[Decision]:
        return [self.decide(f) for f in facts]

    # ---------- the shape a screen reads ----------
    def groups(self, inc) -> list[dict]:
        out = []
        for frame_id in self.frame_ids(inc):
            facts = self.group(inc, frame_id)
            decisions = self.review(facts)
            newest = max(facts, key=lambda f: f.ts)
            out.append({
                "frame_id": frame_id,
                "trigger": newest.provenance.trigger,
                "photo_id": newest.provenance.photo_id,
                "ts": newest.ts.isoformat(),
                "batch_fact_ids": [d.fact_id for d in decisions if d.batchable],
                "individual": [d.as_row() for d in decisions if not d.batchable],
            })
        return out


def default_corroboration(vocabulary: Vocabulary) -> BatchConfirmation:
    return BatchConfirmation(vocabulary, CorroborationRules.from_config())
