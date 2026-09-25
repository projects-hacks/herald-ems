"""The data model of one rendered training example: what the picture shows (the truth) before and after the
photo effects. No drawing and no I/O here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

Box = tuple[float, float, float, float]          # x0, y0, x1, y1 (pixels on the device canvas, later 0-1 in the photo)


@dataclass
class Reading:
    """One fact visible in the picture, in the vocabulary's canonical units (°C, mg/dL, RxNorm ingredient name).

    `shown` is the text as printed ("101.3°F", "METOPROLOL TART 25MG"); `readable` turns False when a finger,
    glare or damage hides it, and an unreadable reading never reaches the target (the prompt says omit it)."""
    key: str
    value: Any
    box: Optional[Box] = None
    shown: str = ""
    readable: bool = True
    strength: Optional[str] = None               # medication labels: canonical strength ("5 mg")
    strength_box: Optional[Box] = None
    strength_readable: bool = True
    why_unreadable: str = ""


@dataclass
class Panel:
    """A rendered device, label or document before it is photographed.

    `image` is RGBA (alpha = the object's silhouette); `hot` are canvas boxes of every value-like number or word on
    it, readings and distractors alike, which occluders use to decide what they cover."""
    image: Any                                    # PIL.Image.Image (RGBA)
    readings: list[Reading]
    family: str                                   # device-layout family, e.g. "oximeter/oled_bars"
    device: str                                   # device type, e.g. "fingertip_oximeter"
    mode: str                                     # capture mode (config/prompts/vision.yaml `modes`)
    texts: list[str] = field(default_factory=list)          # every printed string (for decontamination)
    distractors: list[str] = field(default_factory=list)    # what is on screen that is not a reading
    notes: list[str] = field(default_factory=list)
    flat: bool = False                            # paper or label: photographed flat-ish (no bezel glare)


@dataclass
class Example:
    """A finished training photo: the photo effects applied and boxes mapped into the photo (normalized 0-1)."""
    id: str
    image: Any                                    # PIL.Image.Image (RGB)
    panel: Panel
    degradations: list[str]
    severity: float                               # 0 clean .. 1 hard (sets the target confidence)
    jpeg: bytes = b""                             # the encoded photo as saved (encoded once)
