"""Time- and count-bounded in-memory evidence buffer; nothing is written here."""
from collections import deque

from .types import Frame, GateResult


class FrameBuffer:
    def __init__(self, seconds: float, max_frames: int):
        self.seconds = seconds
        self.items = deque(maxlen=max_frames)

    def clear(self):
        self.items.clear()

    def prune(self, now: float):
        while self.items and self.items[0][0].ts < now - self.seconds:
            self.items.popleft()

    def add(self, frame: Frame, gate: GateResult):
        self.prune(frame.ts)
        self.items.append((frame, gate))

    def best(self, since: float, until: float, roi=None, *, manual=False, refresh=False) -> Frame | None:
        candidates = [(f, g) for f, g in self.items if since <= f.ts <= until
                      and (manual or g.passed or (refresh and g.usable))]
        return max(candidates, key=lambda item: (item[1].sharp, item[0].ts))[0] if candidates else None
