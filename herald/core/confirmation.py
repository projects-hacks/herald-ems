"""Which facts start confirmed. Only confirmed facts count toward scores and leave the vehicle."""
from __future__ import annotations

from typing import Any, Optional

from ..config import load_yaml
from .schema import CapturedBy, Fact, FactIn, Role, Status
from .vocabulary import Vocabulary, norm_value


def calibrated_threshold() -> float:
    return float(load_yaml("confirmation.yaml")["auto_confirm_threshold"])


def room_mic_medic_report_confirms() -> frozenset[str]:
    """Always-tap keys that may still confirm themselves when the check step read them as the medic's own report."""
    return frozenset((load_yaml("confirmation.yaml").get("room_mic") or {}).get("medic_report_confirms") or ())


def room_mic_rules() -> tuple[bool, frozenset[str]]:
    """(room-mic facts may confirm themselves, keys that always wait for a tap), from config/confirmation.yaml."""
    c = load_yaml("confirmation.yaml").get("room_mic") or {}
    return bool(c.get("auto_confirm", False)), frozenset(c.get("always_tap") or ())


def monitor_auto_confirm() -> bool:
    """Whether a reading the camera takes from the patient monitor goes into the record confirmed (config/confirmation.yaml
    `monitor_readings`, the owner's decision of 2026-09-26). Absent means no: nothing confirms itself by default."""
    return bool((load_yaml("confirmation.yaml").get("monitor_readings") or {}).get("auto_confirm", False))


def monitor_reading(f: FactIn) -> bool:
    """A value the camera read off the patient monitor: the device's measurement, captured by the camera. Only the
    capture agent's monitor-mode read of the framed monitor region produces this pair (herald/capture/reading.py); a
    one-shot photo is role=photo, a structured device feed is captured_by=device."""
    return f.captured_by == CapturedBy.camera and f.role == Role.device


def confidence_measure() -> tuple[str, int]:
    """(measure, top alternatives per token) the threshold was calibrated with (herald/extraction/confidence.py)."""
    c = load_yaml("confirmation.yaml").get("confidence") or {}
    return str(c.get("measure", "joint")), int(c.get("top_logprobs", 0))


class ConfirmationPolicy:
    """A fact starts unconfirmed (the medic taps) when it requires a tap by vocabulary (code status), is held
    (`provenance.hold_reason`: said together with a command to the system, or a monitor reading the capture agent's
    jump check did not trust), contradicts an earlier value of a contradiction key, came from a photo or another
    speaker, or is below the auto-confirm confidence (the model's token-probability confidence, threshold calibrated
    in config/confirmation.yaml). A reading the camera took from the patient monitor (`monitor_reading`) is a device
    reading: it is confirmed when config/confirmation.yaml `monitor_readings.auto_confirm` says so, with no
    confidence bar (the vision model's confidence is not calibrated; the rails are the plausibility ranges and the
    jump check). Everything else from the medic's own mic that the model was sure of is confirmed."""

    def __init__(self, vocabulary: Vocabulary, auto_confirm: Optional[float] = None,
                 monitor_confirms: Optional[bool] = None, room_mic: Optional[tuple[bool, frozenset[str]]] = None,
                 medic_report_confirms: Optional[frozenset[str]] = None):
        self.vocab = vocabulary
        self.auto_confirm = auto_confirm if auto_confirm is not None else calibrated_threshold()
        self.monitor_confirms = monitor_confirms if monitor_confirms is not None else monitor_auto_confirm()
        self.room_auto, self.room_always_tap = room_mic if room_mic is not None else room_mic_rules()
        self.room_medic_report = (medic_report_confirms if medic_report_confirms is not None
                                  else room_mic_medic_report_confirms())

    def room_mic_may_confirm(self, fin: FactIn) -> bool:
        """A room-mic fact the check step kept, for a key that does not always need a tap; or an always-tap key in
        `medic_report_confirms` that the check step read as the medic's own report ("giving aspirin 324"). A room-mic
        fact is one with no identified speaker, or one whose speaker the check step read from the words
        (`provenance.heard_as`); a named person's own mic is not the room mic. Confidence, contradictions and command
        holds still apply in initial_status."""
        p = fin.provenance
        if not (self.room_auto and fin.captured_by == CapturedBy.other and p is not None and p.checked):
            return False
        if fin.role != Role.unknown and not p.heard_as:
            return False
        if fin.key in self.room_always_tap:
            return fin.role == Role.medic and p.heard_as == Role.medic.value and fin.key in self.room_medic_report
        return True

    def initial_status(self, fin: FactIn, prev: Optional[Fact], value: Any) -> Status:
        if self.vocab.meta(fin.key).get("require_tap"):
            return Status.unconfirmed
        if fin.provenance is not None and fin.provenance.hold_reason:
            return Status.unconfirmed
        if (fin.key in self.vocab.contradiction_keys and prev is not None
                and norm_value(prev.value) != norm_value(value)):
            return Status.unconfirmed
        if monitor_reading(fin):
            return Status.confirmed if self.monitor_confirms else Status.unconfirmed
        if fin.captured_by == CapturedBy.camera or (fin.captured_by == CapturedBy.other
                                                    and not self.room_mic_may_confirm(fin)):
            return Status.unconfirmed
        return Status.confirmed if fin.confidence >= self.auto_confirm else Status.unconfirmed
