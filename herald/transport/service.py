"""Destination and ETA for the active patient.

The vehicle's position is posted by the medic tablet (or a vehicle GPS); drive times to every county hospital come
from the local road router and are cached per position. The ETA shown and sent is the road route to the confirmed
destination while the position is fresh, otherwise the crew's own estimate (transport.eta_min).

The destination is set by voice or by one tap, never picked from a list in the main flow (owner, 2026-09-26):
- Heard: when the crew's own words name exactly one county hospital (the official name or id, or the local model's
  single pick, `resolver.py`), Herald writes it as the destination itself, confirmed, with what was said and the
  facility id as provenance. A later hospital replaces it (latest wins, audited). Words that name none, or several,
  stay visible as heard and are held for the medic; they are never the destination.
- Suggested: while no destination is set, Herald suggests ONE hospital from the county's own rules
  (`selection.py`), or the hospital another speaker named; the medic accepts it with a tap or by saying it.
Matching runs off the request path (`pending_matches` + `match` in a worker, then `settle` on the event loop).
"""
from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

from ..config import load_yaml
from ..core.confirmation import room_mic_rules
from ..core.schema import CapturedBy, Fact, FactIn, Role, Status, utcnow
from .facilities import Facility, facilities
from .resolver import DestinationResolver, _norm, exact
from .selection import DestinationPolicy, Situation

log = logging.getLogger(__name__)

KEY = "transport.destination"
HEARD = "transport:heard"                    # Herald set it from the crew's own words
SUGGESTED = "medic:destination-suggestion"   # the medic accepted Herald's suggestion
LISTED = "medic:destination-list"            # the medic chose from the county list ("Other hospital…")
HOW = {HEARD: "heard", SUGGESTED: "suggested", LISTED: "chosen", "manual-correction": "chosen"}
NOT_MATCHED = "Not matched to a county hospital"


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
        self._matches: dict[str, Optional[str]] = {}   # normalized heard text -> facility id (None = no single match)
        self._inflight: set[str] = set()
        self._held: set[str] = set()                   # facts Herald held as unmatched: the medic's later word stands
        self._lock = threading.Lock()

    # ---------- the county's hospitals ----------
    def options(self) -> list[Facility]:
        return facilities(self._county())

    def by_name(self, name: str) -> Optional[Facility]:
        said = _norm(name)
        return next((f for f in self.options() if _norm(f.name) == said), None)

    def by_id(self, facility_id: str) -> Optional[Facility]:
        return next((f for f in self.options() if f.id == facility_id), None)

    # ---------- position and drive times ----------
    def _fresh(self, now: datetime) -> bool:
        return self.position is not None and now - self.position["at"] <= self.stale

    async def update_position(self, lat: float, lon: float, accuracy_m: Optional[float], at: Optional[datetime] = None,
                              age_s: Optional[float] = None):
        """`age_s`, the fix's age measured on the device, wins over `at`: a tablet clock that differs from this box's
        would otherwise make a new fix look stale (or from the future)."""
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("position out of range")
        now = self._now()
        if age_s is not None:
            at = now - timedelta(seconds=age_s)
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

    def rows(self, now: Optional[datetime] = None) -> list[dict]:
        """Every county hospital with its drive time, nearest first while the position is fresh."""
        now = now or self._now()
        out = []
        for f in self.options():
            route = self.drive(f.id, now)
            out.append({"id": f.id, "name": f.name, "designations": list(f.designations), "point": f.point,
                        "minutes": round(route[0] / 60) if route else None,
                        "km": round(route[1] / 1000, 1) if route else None})
        out.sort(key=lambda r: (r["minutes"] is None, r["minutes"] or 0, r["name"]))
        return out

    def arrival(self, inc, now: Optional[datetime] = None) -> Optional[datetime]:
        """The road-route arrival time at the confirmed destination, or None (the crew's estimate applies)."""
        now = now or self._now()
        dest = inc.latest(KEY, confirmed_only=True)
        facility = self.by_name(str(dest.value)) if dest else None
        route = self.drive(facility.id, now) if facility else None
        return self._routed_at + timedelta(seconds=route[0]) if route else None

    # ---------- a spoken destination ----------
    def _heard(self, inc) -> Optional[Fact]:
        """The newest destination words that are not a settled destination: anything but a confirmed county
        hospital, a value the medic set, or a value Herald held that the medic then confirmed as said."""
        f = inc.latest(KEY)
        if f is None or (f.status == Status.confirmed and (self.by_name(str(f.value)) or f.id in self._held
                                                           or f.provenance.extractor in HOW)):
            return None
        return f

    def _match_for(self, fact: Fact) -> tuple[Optional[str], bool]:
        """(facility id or None, whether the words have been matched yet)."""
        found = exact(str(fact.value), self.options())
        if found:
            return found, True
        with self._lock:
            key = _norm(str(fact.value))
            return (self._matches[key], True) if key in self._matches else (None, False)

    @staticmethod
    def _from_crew(fact: Fact) -> bool:
        """Words that set the destination without a tap: the crew's own mic, not held by a check; or the room mic
        (the crew is hands-free there, owner's decision 2026-09-26) when the check step kept the words, room-mic facts
        may confirm themselves (config/confirmation.yaml room_mic) and the destination is not a key that always waits."""
        if fact.captured_by == CapturedBy.medic:
            return not fact.provenance.hold_reason
        room_auto, always_tap = room_mic_rules()
        return (fact.captured_by == CapturedBy.other and fact.role == Role.unknown and room_auto
                and KEY not in always_tap and fact.provenance.checked)

    def pending_matches(self, inc) -> list[str]:
        if self.resolver is None:
            return []
        fact = self._heard(inc)
        if fact is None or exact(str(fact.value), self.options()):
            return []
        heard = str(fact.value)
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

    def settle(self, inc) -> Optional[str]:
        """Act on matched words (event loop, after `match`): the crew's words naming one county hospital become the
        destination ("set"); a confirmed value that names none is held for the medic with the reason ("held")."""
        fact = self._heard(inc)
        if fact is None:
            return None
        found, decided = self._match_for(fact)
        if not decided:
            return None
        facility = self.by_id(found) if found else None
        if facility is not None and self._from_crew(fact):
            said = str(fact.value)
            method = "exact" if exact(said, self.options()) else "model"
            fin = FactIn(key=KEY, value=facility.name, role=fact.role, speaker=fact.speaker,
                         captured_by=fact.captured_by, confidence=1.0,
                         provenance=fact.provenance.model_copy(update={
                             "extractor": HEARD, "hold_reason": None,
                             "normalized": [{"said": said, "value": facility.name, "system": "county-facility",
                                             "code": facility.id, "method": method}]}))
            inc.settle(fact.id, fin, actor="herald")
            return "set"
        if facility is None and fact.status == Status.confirmed and fact.id not in self._held:
            self._held.add(fact.id)
            inc.hold_verification(fact.id, NOT_MATCHED)
            return "held"
        return None

    # ---------- what the screen shows ----------
    def _destination(self, fact: Optional[Fact]) -> Optional[dict]:
        if fact is None:
            return None
        facility = self.by_name(str(fact.value))
        said = next((n.get("said") for n in fact.provenance.normalized or [] if n.get("system") == "county-facility"),
                    None)
        return {"fact_id": fact.id, "value": str(fact.value), "id": facility.id if facility else None,
                "how": HOW.get(fact.provenance.extractor or "", "heard"), "said": said, "at": fact.ts.isoformat()}

    def _heard_view(self, fact: Optional[Fact]) -> Optional[dict]:
        if fact is None:
            return None
        found, decided = self._match_for(fact)
        state = ("matched" if found else "unmatched") if decided else ("matching" if self.resolver else "unmatched")
        return {"fact_id": fact.id, "value": str(fact.value), "role": fact.role.value, "state": state, "id": found}

    def suggestion(self, inc, snapshot: Optional[dict], current: Optional[dict], heard: Optional[dict],
                   now: datetime) -> Optional[dict]:
        """ONE hospital to accept: the one another speaker named (when it is not already the destination), else,
        while no destination is set, the county's rule for this situation."""
        if inc.arrived_at or inc.transferred_at or inc.ended_at or inc.disposition:
            return None
        f = self.by_id(heard["id"]) if heard and heard["id"] else None
        if f is not None and (current is None or current["id"] != f.id):
            route = self.drive(f.id, now)
            return {"id": f.id, "name": f.name, "designations": list(f.designations),
                    "minutes": round(route[0] / 60) if route else None,
                    "km": round(route[1] / 1000, 1) if route else None, "nearest_known": route is not None,
                    "basis": "heard", "rule": None, "situation": f"Heard “{heard['value']}” ({heard['role']})",
                    "service": None, "cite": None, "quote": None, "note": None}
        if current is not None or snapshot is None:
            return None
        pick = DestinationPolicy(self._county()).suggest(Situation.of(snapshot, inc.values(confirmed_only=True)),
                                                         self.options(), lambda fid: self.drive(fid, now))
        return {**pick, "basis": "policy"} if pick else None

    def view(self, inc, crew_eta: Optional[dict], now: Optional[datetime] = None,
             snapshot: Optional[dict] = None) -> dict:
        now = now or self._now()
        current = self._destination(inc.latest(KEY, confirmed_only=True))
        heard = self._heard_view(self._heard(inc))
        arrive = self.arrival(inc, now)
        eta = ({"source": "route", "until": arrive.isoformat()} if arrive
               else {"source": "crew", "until": crew_eta["until"]} if crew_eta else None)
        pos = self.position
        return {"routing": self.router is not None, "router_error": self.router_error,
                "position": {"at": pos["at"].isoformat(), "accuracy_m": pos["accuracy_m"], "fresh": self._fresh(now)}
                if pos else None,
                "options": self.rows(now), "destination": current, "heard": heard,
                "suggestion": self.suggestion(inc, snapshot, current, heard, now), "eta": eta}
