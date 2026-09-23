"""County configuration: which stroke scales, which checklist, which destinations, which protocol documents.

Plain reviewed data in config/counties/<id>.json, never written by a model. Switch live with
POST /api/county/<id>; the default comes from HERALD_COUNTY (santa_clara). A protocol document update
flags the county for human review; it never rewrites this file (see herald/protocols.py).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "config" / "counties"
SCALES = {"GFAST": "@gfast", "RACE": "@race"}


def available() -> dict[str, str]:
    return {p.stem: json.loads(p.read_text())["name"] for p in sorted(DIR.glob("*.json"))}


def load(county_id: str) -> dict:
    path = DIR / f"{Path(county_id).name}.json"
    if not path.exists():
        raise KeyError(county_id)
    cfg = json.loads(path.read_text())
    s = cfg["stroke"]
    assert s["primary_scale"] in s["scales"] and all(x in SCALES for x in s["scales"]), "unknown stroke scale"
    return cfg


_ACTIVE = {"cfg": None}


def active() -> dict:
    if _ACTIVE["cfg"] is None:
        _ACTIVE["cfg"] = load(os.getenv("HERALD_COUNTY", "santa_clara"))
    return _ACTIVE["cfg"]


def activate(county_id: str) -> dict:
    _ACTIVE["cfg"] = load(county_id)
    return _ACTIVE["cfg"]


def summary() -> dict:
    c = active()
    return {"id": c["id"], "name": c["name"], "stroke_scales": c["stroke"]["scales"],
            "primary_stroke_scale": c["stroke"]["primary_scale"], "reviewed": c["reviewed"],
            "documents": [{k: d.get(k) for k in ("id", "title", "effective")} for d in c["documents"]]}
