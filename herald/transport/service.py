"""Destination and ETA for the active patient.

The vehicle's position is posted by the medic tablet (or a vehicle GPS); drive times to every county hospital come
from the local road router and are cached per position. The ETA shown and sent is the road route to the confirmed
destination while the position is fresh, otherwise the crew's own estimate (transport.eta_min). A spoken destination
is matched to the county list off the request path (`pending_matches` + `match`, like protocol cues) and offered as a
suggestion; only the medic's tap makes it the destination.
"""
from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

from ..config import load_yaml
from ..core.schema import Status, utcnow
from .facilities import Facility, facilities
from .resolver import DestinationResolver, _norm

log = logging.getLogger(__name__)


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


class TransportService:
    def __init__(self, county: Callable[[], dict], router=None, resolver: Optional[DestinationResolver] = None,
                 config: Optional[dict] = None, clock: Callable[[], datetime] = utcnow):
        cfg = config or load_yaml("transport.yaml")
        self.stale = timedelta(seconds=cfg["position_stale_s"])
        self.moved_m, self.every = cfg["recompute_moved_m"], timedelta(seconds=cfg["recompute_every_s"])
        self.max_accuracy = cfg["max_accuracy_m"]
        self._county, self.router, self.resolver, self._now = county, router, resolver, clock
        self.position: Optional[dict] = None           # {lat, lon, accuracy_m, at}; the vehicle's, not the patient's
        self._routes: dict[str, tuple[float, float]] = {}
        self._routed_at: Optional[datetime] = None
        self._routed_from: Optional[tuple[float, float]] = None
        self.router_error: Optional[str] = None
        self._matches: dict[str, Optional[str]] = {}   # normalized heard text -> facility id (None = no match)
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    # ---------- the county's hospitals ----------
    def options(self) -> list[Facility]:
        return facilities(self._county())

    def by_name(self, name: str) -> Optional[Facility]:
        said = _norm(name)
        return next((f for f in self.options() if _norm(f.name) == said), None)

    # ---------- position and drive times ----------
    def _fresh(self, now: datetime) -> bool:
        return self.position is not None and now - self.position["at"] <= self.stale

    async def update_position(self, lat: float, lon: float, accuracy_m: Optional[float], at: Optional[datetime] = None):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("position out of range")
        now = self._now()
        self.position = {"lat": lat, "lon": lon, "accuracy_m": accuracy_m, "at": min(at or now, now)}
        if self.router is None or (accuracy_m is not None and accuracy_m > self.max_accuracy):
            return
        here = (lat, lon)
        if (self._routed_from and self._routed_at and _metres(here, self._routed_from) < self.moved_m
                and now - self._routed_at < self.every and not self.router_error):
            return
        targets = [f for f in self.options() if f.routable]
        try:
            times = await self.router.table(here, [(f.lat, f.lon) for f in targets])
        except Exception as e:                 # the crew's estimate still works; the screen says routing is down
            self.router_error = f"{type(e).__name__}"[:80]
            log.warning("road routing failed: %s", e)
            return
        self._routes = {f.id: t for f, t in zip(targets, times) if t is not None}
        self._routed_at, self._routed_from, self.router_error = now, here, None

    def drive(self, facility_id: str, now: Optional[datetime] = None) -> Optional[tuple[float, float]]:
        """(seconds, metres) from the vehicle's last fresh routed position, or None."""
        now = now or self._now()
        if not self._fresh(now) or self._routed_at is None or now - self._routed_at > self.stale:
            return None
        return self._routes.get(facility_id)

    def arrival(self, inc, now: Optional[datetime] = None) -> Optional[datetime]:
        """The road-route arrival time at the confirmed destination, or None (the crew's estimate applies)."""
        now = now or self._now()
        dest = inc.latest("transport.destination", confirmed_only=True)
        facility = self.by_name(str(dest.value)) if dest else None
        route = self.drive(facility.id, now) if facility else None
        return self._routed_at + timedelta(seconds=route[0]) if route else None

    # ---------- matching a spoken destination (off the request path) ----------
    def pending_matches(self, inc) -> list[str]:
        if self.resolver is None:
            return []
        dest = inc.latest("transport.destination")
        if dest is None or dest.status != Status.unconfirmed or self.by_name(str(dest.value)):
            return []
        heard = str(dest.value)
        with self._lock:
            key = _norm(heard)
            if key in self._matches or key in self._inflight:
                return []
            self._inflight.add(key)
        return [heard]

    def match(self, heard: str) -> None:
        key = _norm(heard)
        try:
            found = self.resolver.resolve(heard, self.options())
        except Exception as e:                 # try again on the next pass
            log.warning("destination match failed: %s", e)
            with self._lock:
                self._inflight.discard(key)
            return
        with self._lock:
            self._inflight.discard(key)
            self._matches[key] = found

    # ---------- what the screen shows ----------
    def view(self, inc, crew_eta: Optional[dict], now: Optional[datetime] = None) -> dict:
        now = now or self._now()
        fresh = self._fresh(now)
        rows = []
        for f in self.options():
            route = self.drive(f.id, now)
            rows.append({"id": f.id, "name": f.name, "designations": list(f.designations), "point": f.point,
                         "minutes": round(route[0] / 60) if route else None,
                         "km": round(route[1] / 1000, 1) if route else None})
        rows.sort(key=lambda r: (r["minutes"] is None, r["minutes"] or 0, r["name"]))
        dest = inc.latest("transport.destination")
        destination = None
        if dest is not None:
            facility = self.by_name(str(dest.value))
            with self._lock:
                suggested = None if facility else self._matches.get(_norm(str(dest.value)))
            destination = {"fact_id": dest.id, "value": str(dest.value), "status": dest.status.value,
                           "id": facility.id if facility else None, "suggested": suggested,
                           "matching": not facility and suggested is None and _norm(str(dest.value)) in self._inflight}
        arrive = self.arrival(inc, now)
        eta = ({"source": "route", "until": arrive.isoformat()} if arrive
               else {"source": "crew", "until": crew_eta["until"]} if crew_eta else None)
        pos = self.position
        return {"routing": self.router is not None, "router_error": self.router_error,
                "position": {"at": pos["at"].isoformat(), "accuracy_m": pos["accuracy_m"], "fresh": fresh} if pos else None,
                "options": rows, "destination": destination, "eta": eta}
