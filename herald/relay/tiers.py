"""Relay priorities and byte budgets (config/relay.yaml)."""
from __future__ import annotations

from functools import lru_cache

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
