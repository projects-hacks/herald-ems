"""WebSocket fan-out of the full state, with a ping -> pong heartbeat for stale-screen detection."""
from __future__ import annotations

from typing import Callable

from fastapi import WebSocket, WebSocketDisconnect

from ..core.schema import utcnow


class Hub:
    def __init__(self, state: Callable[[], dict]):
        self.state = state
        self.clients: set[WebSocket] = set()

    async def broadcast(self) -> None:
        snap = self.state()
        for ws in list(self.clients):
            try:
                await ws.send_json({"type": "state", "state": snap})
            except Exception:
                self.clients.discard(ws)

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        await ws.send_json({"type": "state", "state": self.state()})
        try:
            while True:
                if await ws.receive_text() == "ping":
                    await ws.send_json({"type": "pong", "t": utcnow().isoformat()})
        except WebSocketDisconnect:
            self.clients.discard(ws)
