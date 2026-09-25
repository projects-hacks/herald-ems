"""One persistent, bounded WebSocket camera for a timed rehearsal. No inference code."""
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import urlsplit, urlunsplit

from websockets.sync.client import connect


class FrameReplay:
    def __init__(self, url, fps=1):
        parts = urlsplit(url)
        self.url = urlunsplit(("wss" if parts.scheme == "https" else "ws", parts.netloc, "/ws/frames", "", ""))
        self.period = 1 / fps
        self.lock, self.stopped = Lock(), Event()
        self.paths, self.index, self.error = [], 0, None
        self.thread = None

    def select(self, spec):
        self.check()
        folder = Path(spec["folder"])
        paths = [folder / name for name in spec["files"]] if "files" in spec else sorted(folder.glob("*.jpg"))
        if not paths or any(not p.is_file() or p.stat().st_size > 1024 * 1024 for p in paths):
            raise ValueError("replay needs existing JPEGs, each at most 1 MiB")
        with self.lock:
            self.paths, self.index = paths, 0
        if self.thread is None:
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        try:
            with connect(self.url, open_timeout=5, close_timeout=2, proxy=None) as ws:
                while not self.stopped.is_set():
                    with self.lock:
                        path = self.paths[min(self.index, len(self.paths) - 1)]
                        self.index = min(self.index + 1, len(self.paths) - 1)
                    ws.send(path.read_bytes())
                    ws.recv(timeout=5)  # receive every acknowledgement: no unbounded backlog
                    self.stopped.wait(self.period)
        except Exception as e:
            self.error = e

    def check(self):
        if self.error:
            raise RuntimeError(f"camera replay stopped: {self.error}") from self.error

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=8)
