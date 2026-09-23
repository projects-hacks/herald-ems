"""County configuration: which stroke scales, which checklist, which destinations, which protocol documents.

Reviewed data in config/counties/<id>.json, never written by a model. A protocol document update flags the
county for human review; it never rewrites the file. `CountyRegistry` holds the active county; switch it live
with POST /api/county/<id>.
"""
from __future__ import annotations

import json
from pathlib import Path

from .loader import CONFIG_DIR

SCALE_ITEMS = {"GFAST": "@gfast", "RACE": "@race"}     # checklist item meaning "that scale is complete"
SCALE_IDS = {"GFAST": "gfast", "RACE": "race"}         # scale name in a county file -> config/scores/<id>.yaml


class CountyRegistry:
    def __init__(self, default_id: str, directory: Path = CONFIG_DIR / "counties"):
        self.dir = directory
        self._active = self.load(default_id)

    def available(self) -> dict[str, str]:
        return {p.stem: json.loads(p.read_text())["name"] for p in sorted(self.dir.glob("*.json"))}

    def load(self, county_id: str) -> dict:
        path = self.dir / f"{Path(county_id).name}.json"
        if not path.exists():
            raise KeyError(county_id)
        cfg = json.loads(path.read_text())
        s = cfg["stroke"]
        if s["primary_scale"] not in s["scales"] or not all(x in SCALE_ITEMS for x in s["scales"]):
            raise ValueError(f"{county_id}: unknown stroke scale in {s['scales']}")
        return cfg

    @property
    def active(self) -> dict:
        return self._active

    def activate(self, county_id: str) -> dict:
        self._active = self.load(county_id)
        return self._active

    def summary(self) -> dict:
        c = self._active
        return {"id": c["id"], "name": c["name"], "stroke_scales": c["stroke"]["scales"],
                "primary_stroke_scale": c["stroke"]["primary_scale"], "reviewed": c["reviewed"],
                "documents": [{k: d.get(k) for k in ("id", "title", "effective")} for d in c["documents"]]}
