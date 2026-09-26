"""How an encounter ended (config/dispositions.yaml): the medic's choice when finishing, with its NEMSIS codes.
Only an outcome that is a transport by this unit has a destination, an ETA and ED delivery."""
from __future__ import annotations

from typing import Optional


class Dispositions:
    def __init__(self, config: dict):
        self.outcomes: list[dict] = config["outcomes"]
        self._by_id = {o["id"]: o for o in self.outcomes}

    def get(self, outcome_id: Optional[str]) -> Optional[dict]:
        return self._by_id.get(outcome_id) if outcome_id else None

    def transports(self, outcome_id: Optional[str]) -> bool:
        outcome = self.get(outcome_id)
        return bool(outcome and outcome["transport"])
