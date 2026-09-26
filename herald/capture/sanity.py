"""The capture agent's sanity check on a monitor reading before it enters the record as a device reading.

A reading the camera takes from the patient monitor goes into the record confirmed (config/confirmation.yaml
`monitor_readings`). This check is what keeps a misread from doing that silently: a value that moved further than
`monitor.jump.max_step` from the previous monitor reading of the same vital, taken within `window_s`, is held for the
medic with the configured reason. The references are the newest trusted monitor reading (confirmed, or never held)
and any held reading after it: agreeing with either is enough, so a transient misread does not drag the next correct
reading into Needs you, and a real change is recorded on its second reading because it repeats. The limits and the
wording are content (config/capture.yaml); this module is the engine. No I/O.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable, Optional

from ..core.confirmation import monitor_reading
from ..core.schema import Fact, FactIn, Status


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _seen_at(f) -> datetime:
    return f.provenance.observed_at or f.ts


def _fmt(n) -> str:
    return f"{n:g}" if isinstance(n, float) else str(n)


class MonitorJumpCheck:
    def __init__(self, config: dict, label: Callable[[str], str]):
        self.window = float(config["window_s"])
        self.steps = {key: float(step) for key, step in config["max_step"].items()}
        self.wording = config["reason"]
        self.label = label

    def reason(self, reading: FactIn, history: Iterable[Fact], at: datetime) -> Optional[str]:
        """Why this reading is held, or None when it may be recorded as a device reading. `history` is the key's
        facts (rejected ones already left out), oldest first; `at` is when this reading's frame was seen."""
        limit = self.steps.get(reading.key)
        if limit is None or not _number(reading.value):
            return None
        recent = [f for f in history if monitor_reading(f) and _number(f.value)
                  and 0 <= (at - _seen_at(f)).total_seconds() <= self.window]
        trusted, held = None, None
        for f in reversed(recent):
            if f.status == Status.confirmed or not f.provenance.hold_reason:
                trusted = f
                break
            held = held or f               # the newest held reading after the newest trusted one
        references = [f for f in (trusted, held) if f is not None]
        if not references or any(abs(reading.value - f.value) <= limit for f in references):
            return None
        ref = trusted or held
        return self.wording.format(label=self.label(reading.key), value=_fmt(reading.value), previous=_fmt(ref.value),
                                   delta=_fmt(round(abs(reading.value - ref.value), 1)),
                                   seconds=round((at - _seen_at(ref)).total_seconds()), limit=_fmt(limit))
