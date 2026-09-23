"""Which facts start confirmed. Only confirmed facts count toward scores and leave the vehicle."""
from __future__ import annotations

from typing import Any, Optional

from .schema import CapturedBy, Fact, FactIn, Status
from .vocabulary import Vocabulary, norm_value


class ConfirmationPolicy:
    """A fact starts unconfirmed (the medic taps) when it requires a tap by vocabulary (code status), came from a
    photo or another speaker, contradicts an earlier value of a contradiction key, or is below the auto-confirm
    confidence. Everything else the medic said with high confidence is confirmed."""

    def __init__(self, vocabulary: Vocabulary, auto_confirm: float = 0.85):
        self.vocab = vocabulary
        self.auto_confirm = auto_confirm

    def initial_status(self, fin: FactIn, prev: Optional[Fact], value: Any) -> Status:
        if self.vocab.meta(fin.key).get("require_tap"):
            return Status.unconfirmed
        if fin.captured_by in (CapturedBy.camera, CapturedBy.other):
            return Status.unconfirmed
        if (fin.key in self.vocab.contradiction_keys and prev is not None
                and norm_value(prev.value) != norm_value(value)):
            return Status.unconfirmed
        return Status.confirmed if fin.confidence >= self.auto_confirm else Status.unconfirmed
