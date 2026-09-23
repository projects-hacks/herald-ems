"""Loads every score definition in config/scores/ into its engine."""
from __future__ import annotations

from functools import lru_cache

from ..config import CONFIG_DIR, load_yaml
from .banded import BandedScore
from .criteria import CriteriaScore
from .item_sum import ItemSumScale

ENGINES = {"banded": BandedScore, "item_sum": ItemSumScale, "criteria": CriteriaScore}


class ScaleRegistry:
    def __init__(self, scales: dict):
        self.scales = scales

    @classmethod
    def from_config(cls, directory: str = "scores") -> "ScaleRegistry":
        scales = {}
        for path in sorted((CONFIG_DIR / directory).glob("*.yaml")):
            d = load_yaml(f"{directory}/{path.name}")
            scales[d["id"]] = ENGINES[d["kind"]](d)
        return cls(scales)

    def __getitem__(self, scale_id: str):
        return self.scales[scale_id]

    def __contains__(self, scale_id: str) -> bool:
        return scale_id in self.scales

    def ids(self) -> list[str]:
        return list(self.scales)

    def item_scales(self) -> list[ItemSumScale]:
        return [s for s in self.scales.values() if isinstance(s, ItemSumScale)]

    def evaluate_all(self, values: dict) -> dict[str, dict]:
        return {sid: s.evaluate(values) for sid, s in self.scales.items()}


@lru_cache(maxsize=1)
def default_scales() -> ScaleRegistry:
    return ScaleRegistry.from_config()
