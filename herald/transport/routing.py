"""Road drive times from a local OSRM server (car profile). One table request gives the time to every hospital."""
from __future__ import annotations

from typing import Optional

import httpx


class OsrmRouter:
    def __init__(self, url: str, timeout: float = 3.0, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.url, self.timeout, self._transport = url.rstrip("/"), timeout, transport

    async def table(self, origin: tuple[float, float],
                    destinations: list[tuple[float, float]]) -> list[Optional[tuple[float, float]]]:
        """(seconds, metres) from origin (lat, lon) to each destination; None where no road route exists."""
        if not destinations:
            return []
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in [origin, *destinations])
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            r = await client.get(f"{self.url}/table/v1/driving/{coords}",
                                 params={"sources": "0", "annotations": "duration,distance"})
            r.raise_for_status()
            data = r.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"router: {data.get('code')}")
        durations, distances = data["durations"][0][1:], data["distances"][0][1:]
        return [None if d is None or m is None else (float(d), float(m)) for d, m in zip(durations, distances)]
