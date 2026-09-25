"""Relay priorities, byte budgets, and consent scopes (config/relay.yaml)."""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from ..config import load_yaml


class RelayTiers:
    def __init__(self, tiers: list[dict], budget: dict[str, int], triage_rank: dict[str, int] | None = None):
        self.tiers = tiers
        self.budget = budget
        self.triage_rank = triage_rank or {"unknown": 1}
        self.priority = {k: (t["tier"], t["why"]) for t in tiers for k in t["keys"]}

    @classmethod
    def from_config(cls, rel: str = "relay.yaml") -> "RelayTiers":
        d = load_yaml(rel)
        return cls(d["tiers"], d["budget_bytes"], d["triage_rank"])

    def __contains__(self, key: str) -> bool:
        return key in self.priority

    def why(self, key: str) -> str:
        return self.priority[key][1]


@lru_cache(maxsize=1)
def default_tiers() -> RelayTiers:
    return RelayTiers.from_config()


class RelayScopes:
    """What an authorized scope actually lets flow (`config/relay.yaml` `scopes`): which relay tiers (1-5,
    `RelayTiers`) it may send at all.

    A scope id is one of the checklist alert ids the medic actually had open when they authorized the destination
    (`herald/api/context.py` `pre_alert_scope`), never free text from a client. A same-purpose alert pre-alert
    (stroke, trauma, sepsis, STEMI) authorizes the clinical picture the receiving team needs before arrival: what's
    critical, whether the published score changed, and current vitals/exam. Arrival logistics and demographics are
    not part of that consent; they flow once a broader `default_scope` authorization is in force (no specific alert
    checklist open when the medic authorized), which is the unrestricted, every-tier send. Multiple alerts open at
    once take the union of their ceilings.
    """

    def __init__(self, scopes: dict[str, dict], default_scope: str):
        self.scopes = scopes
        self.default_scope = default_scope

    @classmethod
    def from_config(cls, rel: str = "relay.yaml") -> "RelayScopes":
        d = load_yaml(rel)
        return cls(d.get("scopes", {}), d.get("default_scope", "patient_update"))

    def ceiling(self, alert_ids: Sequence[str]) -> set[int]:
        ids = [i for i in alert_ids if i in self.scopes] or [self.default_scope]
        out: set[int] = set()
        for sid in ids:
            out.update(self.scopes[sid].get("ceiling", []))
        return out

    def allowed_keys(self, alert_ids: Sequence[str], tiers: "RelayTiers") -> frozenset[str]:
        ceiling = self.ceiling(alert_ids)
        return frozenset(key for key, (tier, _why) in tiers.priority.items() if tier in ceiling)


@lru_cache(maxsize=1)
def default_scopes() -> RelayScopes:
    return RelayScopes.from_config()
