"""Which facts start confirmed. Only confirmed facts count toward scores and leave the vehicle."""
from __future__ import annotations

from typing import Any, Optional

from ..config import load_yaml
from .schema import CapturedBy, Fact, FactIn, Status
from .vocabulary import Vocabulary, norm_value


def calibrated_threshold() -> float:
    return float(load_yaml("confirmation.yaml")["auto_confirm_threshold"])


def confidence_measure() -> tuple[str, int]:
    """(measure, top alternatives per token) the threshold was calibrated with (herald/extraction/confidence.py)."""
    c = load_yaml("confirmation.yaml").get("confidence") or {}
    return str(c.get("measure", "joint")), int(c.get("top_logprobs", 0))


class ConfirmationPolicy:
    """A fact starts unconfirmed (the medic taps) when it requires a tap by vocabulary (code status), came from a
    photo or another speaker, is held (said together with a command to the system: `provenance.hold_reason`, whatever
    its confidence), contradicts an earlier value of a contradiction key, or is below the auto-confirm
    confidence (the model's token-probability confidence, threshold calibrated in config/confirmation.yaml).
    Everything else from the medic's own mic that the model was sure of is confirmed."""

    def __init__(self, vocabulary: Vocabulary, auto_confirm: Optional[float] = None):
        self.vocab = vocabulary
        self.auto_confirm = auto_confirm if auto_confirm is not None else calibrated_threshold()

    def initial_status(self, fin: FactIn, prev: Optional[Fact], value: Any) -> Status:
        if self.vocab.meta(fin.key).get("require_tap"):
            return Status.unconfirmed
        if fin.captured_by in (CapturedBy.camera, CapturedBy.other):
            return Status.unconfirmed
        if fin.provenance is not None and fin.provenance.hold_reason:
            return Status.unconfirmed
        if (fin.key in self.vocab.contradiction_keys and prev is not None
                and norm_value(prev.value) != norm_value(value)):
            return Status.unconfirmed
        return Status.confirmed if fin.confidence >= self.auto_confirm else Status.unconfirmed
