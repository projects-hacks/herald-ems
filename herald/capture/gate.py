"""Cheap CPU image-quality/change gate. Baseline advances only after a read is accepted."""
import io

import numpy as np
from PIL import Image

from .types import Frame, GateResult, ROI


class FrameGate:
    def __init__(self, config: dict):
        self.config = config
        self.baseline = None
        self.current = None

    def clear(self):
        self.baseline = self.current = None

    def assess(self, frame: Frame, roi: ROI | None = None) -> GateResult:
        c = self.config
        with Image.open(io.BytesIO(frame.jpeg)) as im:
            im = im.convert("L")
            if roi:
                im = im.crop(roi.box(frame.w, frame.h))
            im.thumbnail((c["width"], c["width"]))
            grey = np.asarray(im, dtype=np.float32)
        self.current = grey
        bright = float(grey.mean())
        p = np.pad(grey, 1, mode="edge")
        lap = p[1:-1, :-2] + p[1:-1, 2:] + p[:-2, 1:-1] + p[2:, 1:-1] - 4 * grey
        sharp = float(lap.var())
        changed = (float(np.abs(grey - self.baseline).mean() / 255)
                   if self.baseline is not None and grey.shape == self.baseline.shape else 1.0)
        quality = c["bright_min"] <= bright <= c["bright_max"] and sharp >= c["sharp_min"]
        passed = quality and changed >= c["change_min"]
        reason = ("dark" if bright < c["bright_min"] else "bright" if bright > c["bright_max"] else
                  "blurred" if sharp < c["sharp_min"] else "changed" if passed else "unchanged")
        return GateResult(sharp, changed, bright, passed, reason, quality)

    def accept(self, frame: Frame, roi: ROI | None = None):
        self.assess(frame, roi)
        self.baseline = self.current.copy()
