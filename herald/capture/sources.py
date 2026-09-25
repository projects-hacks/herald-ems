"""Bounded browser ingestion and CPU-only replay; sources never call a model."""
from collections import deque
from pathlib import Path
from time import time

from .frames import decode_frame


class BrowserFrameSource:
    def __init__(self, max_frames=1):
        self.pending = deque(maxlen=max_frames)

    def push(self, frame):
        self.pending.append(frame)

    def frames(self):
        while self.pending:
            yield self.pending.popleft()

    def close(self):
        self.pending.clear()


class ReplayFrameSource:
    def __init__(self, folder: Path, fps: float, config: dict, clock=time):
        self.folder, self.fps, self.config, self.clock = Path(folder), fps, config, clock
        self.closed = False

    def frames(self):
        self.closed = False
        for path in sorted(self.folder.glob("*.jpg")):
            if self.closed:
                break
            if path.stat().st_size > self.config["max_frame_bytes"]:
                continue
            yield decode_frame(path.read_bytes(), self.clock(), "replay", self.config)

    def close(self):
        self.closed = True
