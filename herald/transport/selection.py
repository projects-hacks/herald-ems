"""The ONE destination Herald suggests while none is set.

The county's own rules (config/counties/<id>.json `destinations.selection.rules`, quoted from its destination policy)
are read in order and the first whose conditions hold picks the hospital lists (e.g. `comprehensive_stroke`, from
Policy 602 Table B). The closest listed hospital by road wins; without a road time for any of them, the first in the
list's order, and the suggestion says the nearest is not known. A rule may name a time limit (`over_minutes`) past
which another list applies (700-A13 §3.2.1: over 45 minutes to the closest Comprehensive Stroke Center, the closest
Primary Stroke Center). Every condition, list, limit and quote is data; nothing clinical is written here.

Conditions (`when`, all must hold; an empty `when` always holds):
  alert   a checklist id that is open for this call (Snapshot.readiness)
  scores  [{id, field, equals}]: a computed score's field (from confirmed values) equals the value
  facts   a criterion rule (herald/scoring/rules.py) over the confirmed values; undecided is not met
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..scoring.rules import evaluate
from .facilities import Facility

Drive = Callable[[str], Optional[tuple[float, float]]]      # facility id -> (seconds, metres) by road, or None


@dataclass(frozen=True)
class Situation:
    alerts: frozenset = frozenset()          # open checklist ids
    scores: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)

    @classmethod
    def of(cls, snapshot: dict, values: dict[str, Any]) -> "Situation":
        return cls(frozenset(r["id"] for r in snapshot.get("readiness", [])), snapshot.get("scores") or {}, values)


class DestinationPolicy:
    def __init__(self, county: dict):
        self.dest = county.get("destinations") or {}
        self.rules: list[dict] = (self.dest.get("selection") or {}).get("rules", [])

    # ---------- the county's rules ----------
    @staticmethod
    def _holds(when: dict, s: Situation) -> bool:
        if "alert" in when and when["alert"] not in s.alerts:
            return False
        if any((s.scores.get(c["id"]) or {}).get(c["field"]) != c["equals"] for c in when.get("scores", [])):
            return False
        return "facts" not in when or evaluate(when["facts"], s.values).met is True

    def rule_for(self, s: Situation) -> Optional[dict]:
        return next((r for r in self.rules if self._holds(r.get("when") or {}, s)), None)

    def members(self, lists: list[str], options: list[Facility]) -> list[Facility]:
        """The county's hospitals on any of the lists, in list order; every hospital when no list is named."""
        if not lists:
            return list(options)
        by_id, out = {f.id: f for f in options}, []
        for name in lists:
            for fid in self.dest.get(name, []):
                if fid in by_id and by_id[fid] not in out:
                    out.append(by_id[fid])
        return out

    @staticmethod
    def _closest(members: list[Facility], drive: Drive) -> Optional[tuple[Facility, Optional[tuple[float, float]]]]:
        if not members:
            return None
        routed = [(f, r) for f, r in ((f, drive(f.id)) for f in members) if r is not None]
        return min(routed, key=lambda fr: fr[1][0]) if routed else (members[0], None)

    # ---------- the suggestion ----------
    def suggest(self, s: Situation, options: list[Facility], drive: Drive) -> Optional[dict]:
        rule = self.rule_for(s)
        pick = self._closest(self.members(rule["lists"], options), drive) if rule else None
        if pick is None:
            return None
        why = rule
        over = rule.get("over_minutes")
        if over and pick[1] is not None and pick[1][0] / 60 > over["minutes"]:
            alt = self._closest(self.members(over["lists"], options), drive)
            if alt is not None:
                pick, why = alt, over
        facility, route = pick
        return {"id": facility.id, "name": facility.name, "designations": list(facility.designations),
                "minutes": round(route[0] / 60) if route else None, "km": round(route[1] / 1000, 1) if route else None,
                "nearest_known": route is not None, "rule": rule["id"], "situation": rule["situation"],
                "service": why["service"], "cite": why["cite"], "quote": why["quote"], "note": rule.get("note")}

    # ---------- checks on the data ----------
    def problems(self, options: list[Facility]) -> list[str]:
        ids, out = {f.id for f in options}, []
        for r in self.rules:
            for part in (r, r.get("over_minutes") or {}):
                for name in part.get("lists", []):
                    listed = self.dest.get(name)
                    if not isinstance(listed, list):
                        out.append(f"{r['id']}: no destination list '{name}'")
                    elif set(listed) - ids:
                        out.append(f"{r['id']}: '{name}' names hospitals not on the list: {sorted(set(listed) - ids)}")
            for k in ("id", "situation", "service", "cite", "quote"):
                if not r.get(k):
                    out.append(f"{r.get('id', '?')}: missing {k}")
        return out
