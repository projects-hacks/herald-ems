"""Photo -> facts with the local vision-language model (prompts and ranges: config/prompts/vision.yaml).

Every fact from a photo starts unconfirmed; the medic taps to confirm. Reading only: no ECG interpretation, no
advice. Readings outside the (tighter) photo plausibility ranges are dropped, and an SBP at or below its DBP
drops the pair. Drug names on a label are normalized to RxNorm by the injected `FactCoder`."""
from __future__ import annotations

import base64
from typing import Optional

from ..config import load_yaml
from ..core.ports import FactCoder, TextModel
from ..core.schema import CapturedBy, FactIn, Provenance, Role


class VisionReader:
    """The `PhotoReader` interface over a local vision-capable `TextModel`."""

    def __init__(self, model: TextModel, coder: Optional[FactCoder] = None):
        cfg = load_yaml("prompts/vision.yaml")
        self.model = model
        self.coder = coder
        self.system = cfg["system"]
        self.prompts: dict[str, str] = cfg["modes"]
        self.ranges = {k: tuple(v) for k, v in cfg["plausible_ranges"].items()}
        self.modes = tuple(self.prompts)

    def read(self, image_bytes: bytes, mode: str, photo_id: Optional[str] = None) -> list[FactIn]:
        if mode not in self.prompts:
            raise ValueError(f"mode must be one of {list(self.prompts)}")
        data = self.model.chat_json(self.system, self.prompts[mode],
                                    image_b64=base64.b64encode(image_bytes).decode(), max_tokens=400)
        tag = f"vision:{self.model.model_name()}"
        out: list[FactIn] = []
        for f in data.get("facts", []):
            key, value = f.get("key"), f.get("value")
            if key is None or value in (None, "", []) or not self._plausible(key, value):
                continue
            prov = Provenance(photo_id=photo_id, crop=_box(f.get("box")), extractor=tag,
                              text=f.get("strength") and f"{value} {f['strength']}")
            common = dict(role=Role.photo, speaker=mode.replace("_", " "), captured_by=CapturedBy.camera,
                          confidence=_confidence(f.get("confidence")), provenance=prov)
            out.append(FactIn(key=key, value=value, **common))
        sbp = next((f.value for f in out if f.key == "vitals.sbp"), None)
        dbp = next((f.value for f in out if f.key == "vitals.dbp"), None)
        if sbp is not None and dbp is not None and float(dbp) >= float(sbp):
            out = [f for f in out if f.key not in ("vitals.sbp", "vitals.dbp")]
        return self.coder.code(out) if self.coder else out

    def _plausible(self, key: str, value) -> bool:
        if key not in self.ranges:
            return True
        try:
            lo, hi = self.ranges[key]
            return lo <= float(value) <= hi
        except (TypeError, ValueError):
            return False


def _box(box) -> Optional[list[float]]:
    """The model's box for the reading, or None when it is not four numbers (a malformed box must not cost the
    reading itself: the photo stays the evidence)."""
    if isinstance(box, (list, tuple)) and len(box) == 4:
        try:
            return [float(x) for x in box]
        except (TypeError, ValueError):
            return None
    return None


def _confidence(c) -> float:
    try:
        return min(1.0, max(0.0, float(c)))
    except (TypeError, ValueError):
        return 0.8
