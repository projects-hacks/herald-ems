"""The active county's receiving hospitals (config/counties/<id>.json `destinations`), with the designations its
destination policy lists and the point a road route ends at."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    designations: tuple[str, ...]          # e.g. ("Comprehensive Stroke Center",), as the county's table names them
    lat: Optional[float] = None
    lon: Optional[float] = None
    point: Optional[str] = None            # "emergency entrance" or "campus": what the coordinates mark

    @property
    def routable(self) -> bool:
        return self.lat is not None and self.lon is not None


def facilities(county: dict) -> list[Facility]:
    dest = county.get("destinations") or {}
    services = ((dest.get("audit") or {}).get("services") or {})
    locations = dest.get("locations") or {}
    out = []
    for fid, name in (dest.get("facilities") or {}).items():
        where = locations.get(fid) or {}
        out.append(Facility(fid, name, tuple(label for key, label in services.items() if fid in dest.get(key, [])),
                            where.get("lat"), where.get("lon"), where.get("point")))
    return out
