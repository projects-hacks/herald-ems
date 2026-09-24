"""Loads every score definition in config/scores/ into its engine."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

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

    def ids(self, county: Optional[str] = None) -> list[str]:
        """Every score, or with a county: the published scores plus that county's own criteria (`county:`)."""
        return [sid for sid, s in self.scales.items()
                if county is None or getattr(s, "county", None) in (None, county)]

    def item_scales(self) -> list[ItemSumScale]:
        return [s for s in self.scales.values() if isinstance(s, ItemSumScale)]

    def evaluate_all(self, values: dict, county: Optional[str] = None) -> dict[str, dict]:
        return {sid: self.scales[sid].evaluate(values) for sid in self.ids(county)}


@lru_cache(maxsize=1)
def default_scales() -> ScaleRegistry:
    return ScaleRegistry.from_config()
