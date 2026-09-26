"""Mock emergency-department receiver. A plain HTTP service with no AI.

Run it on a DIFFERENT machine or network from the Nano (e.g., a teammate's laptop), so the
link between them can be degraded for real:
    python -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200
Idempotent by sequence number: a retried packet is acknowledged again but never applied twice.

B7: this service is meant to be reachable on a real network (the whole point is a degradable link to a
different machine), so its two mutating endpoints, /ingest and /reset, are gated by ED_RECEIVER_TOKEN -- a
shared secret, unset by default (open, for local rehearsal). Set it to the same value Herald sends as
HERALD_ED_TOKEN (herald/config/settings.py, herald/relay/relay.py) before running this on a network you don't
trust. /ping, /state and /ws stay open: they carry nothing back to the ambulance and reading them costs nothing.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Herald ED receiver")
INCIDENTS: dict[str, dict] = {}
CLIENTS: set[WebSocket] = set()
LINK = {"last_contact_at": None}   # any request from the ambulance (packet or idle probe)
TOKEN_HEADER = "x-herald-token"


def _check_token(x_herald_token: str | None = Header(default=None, alias=TOKEN_HEADER)) -> None:
    expected = os.environ.get("ED_RECEIVER_TOKEN")
    if expected and x_herald_token != expected:
        raise HTTPException(401, "missing or invalid device token (X-Herald-Token)")


def _key_meta(meta: dict) -> dict:
    """Display metadata for one vocabulary key: label, unit and type, so the screen can show "142 mg/dL".
    The unit is the one config/vocabulary.yaml declares; a numeric key whose label carries the unit as a
    parenthesized suffix instead ("ETA (min)") lends it from there. Either way the label drops the suffix."""
    label, unit = meta["label"], meta.get("unit")
    suffix = re.fullmatch(r"(?P<base>.+?)\s*\((?P<word>[^\s\d()]+)\)", label)
    if suffix and (suffix["word"] == unit or (unit is None and meta.get("type") in ("int", "float"))):
        label, unit = suffix["base"], unit or suffix["word"]
    return {"label": label, "unit": unit, "type": meta.get("type")}


@app.get("/api/meta")
async def metadata():
    from herald.config import load_yaml
    from herald.core.vocabulary import default_vocabulary
    from herald.scoring import default_scales
    keys = {key: _key_meta(meta) for key, meta in default_vocabulary().keys.items()}
    scales = default_scales()
    # `not_met`: the line a criteria score sends when it is complete and not met, so a header alert badge shows only
    # for a met result (config/ed_display.yaml `alerts`).
    keys.update({f"score.{sid}": {"label": scales[sid].name, "unit": None, "type": None,
                                  "not_met": scales[sid].d.get("relay_text_not_met")}
                 for sid in scales.ids()})
    keys.update({key: {"label": text, "unit": None, "type": None}      # route ETA, "not transported", readiness
                 for key, text in load_yaml("relay.yaml").get("derived_labels", {}).items()})
    display = load_yaml("ed_display.yaml")
    checklists = load_yaml("checklists.yaml").get("alerts", {})
    # The relayed `alert.readiness` line names each open checklist by its label; the badge matches on that label.
    display["alerts"] = [{**alert, "readiness_label": checklists.get(alert.get("checklist"), {}).get("label")}
                         for alert in display.get("alerts", [])]
    return {"keys": keys, "display": display}


@app.get("/api/handoff/{patient_id}")
async def handoff(patient_id: str, format: str | None = None):
    from .report import received_report
    if patient_id not in INCIDENTS:
        raise HTTPException(404, "No received patient with that ID")
    try:
        return received_report(patient_id, INCIDENTS[patient_id], format)
    except KeyError:
        raise HTTPException(400, "Unknown handoff format")


class Acknowledgement(BaseModel):
    status: str
    note: str | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


_RANGES = None


def _severity(fields: dict) -> dict[str, str]:
    """Where each received vital sits on the adult NEWS2-derived bands (config/vital_ranges.yaml): "abnormal" or
    "critical", absent when normal. The same colouring the medic's screen uses, computed from received values only.
    It withdraws for the patients NEWS2 excludes (a received paediatric age or pregnancy), exactly as on the vehicle
    (herald/core/snapshot.py `_vitals_applicable`). A display aid, never a decision."""
    global _RANGES
    from herald.config import load_yaml
    from herald.core.vital_severity import VitalRanges
    from herald.scoring import default_scales
    if _RANGES is None:
        _RANGES = VitalRanges.from_config(load_yaml)
    values = {key: field["v"] for key, field in fields.items()}
    applicable = default_scales()["news2"].evaluate(values).get("applicability") != "excluded"
    spo2_scale = 2 if values.get("patient.spo2_scale") == 2 else 1
    out = {}
    for key in _RANGES.keys():
        level = _RANGES.severity(key, values[key], applicable=applicable, spo2_scale=spo2_scale) if key in values else None
        if level:
            out[key] = level
    return out


def view() -> dict:
    return {"incidents": INCIDENTS, "last_contact_at": LINK["last_contact_at"]}


async def push() -> None:
    for ws in list(CLIENTS):
        try:
            await ws.send_json(view())
        except Exception:
            CLIENTS.discard(ws)


@app.post("/ingest", dependencies=[Depends(_check_token)])
async def ingest(req: Request):
    raw = await req.body()
    LINK["last_contact_at"] = now()
    p = json.loads(raw)
    inc = INCIDENTS.setdefault(p["i"], {"fields": {}, "history": {}, "packets": [], "applied": [],
                                        "duplicates": 0, "bytes": 0, "timeline": [], "dest": p.get("dest"),
                                        "audit": [], "label": p.get("patient") or p["i"],
                                        "queued_on_rig": 0, "first_at": now()})
    if p.get("patient"):
        inc["label"] = p["patient"]
    if p["q"] in inc["applied"]:
        inc["duplicates"] += 1
        await push()
        return {"ack": p["q"], "duplicate": True}
    for k, v in p.get("f", {}).items():
        if inc["fields"].get(k, {}).get("v") != v:
            if k == "stroke.lkw":
                inc.pop("lkw_at", None)
            inc["history"].setdefault(k, []).append({"v": v, "t": now()})
            inc["fields"][k] = {"v": v, "seq": p["q"], "t": now()}
        # an unchanged value keeps the sequence and time it first arrived with: a full sync re-sends everything, and
        # re-stamping would reset the ETA countdown and mark every field as just updated
    for key in p.get("rm", []):
        if key == "stroke.lkw":
            inc.pop("lkw_at", None)
        previous = inc["fields"].pop(key, None)
        inc["audit"].append({"at": now(), "action": "withdrawn", "key": key, "seq": p["q"],
                             "previous": previous["v"] if previous else None})
    if "tl" in p:
        inc["timeline"] = p["tl"]
        inc["lkw_at"] = p.get("lkw_at")
    if p.get("tier") == "handover" and isinstance(p.get("ho"), dict):
        # The vehicle's final packet: the handoff report frozen when the medic handed the patient over. `arrived_at`
        # is this screen's own clock, so a "received" acknowledgement is compared on one clock.
        inc["handover"] = {**p["ho"], "seq": p["q"], "arrived_at": now()}
    try:
        inc["severity"] = _severity(inc["fields"])
    except Exception:   # a display aid never costs a packet: an uncolourable value leaves the tiles neutral
        logging.getLogger(__name__).exception("vital severity unavailable for %s", p["i"])
        inc["severity"] = {}
    inc["applied"].append(p["q"])
    inc["bytes"] += len(raw)
    inc["queued_on_rig"] = p.get("x", 0)
    inc["packets"].append({"seq": p["q"], "tier": p.get("tier"), "bytes": len(raw),
                           "keys": list(p.get("f", {}).keys()), "removed": p.get("rm", []), "at": now()})
    await push()
    return {"ack": p["q"]}


@app.get("/ping")
async def ping():
    LINK["last_contact_at"] = now()
    await push()
    return {"ok": True}


@app.get("/state")
async def state():
    return view()


@app.post("/reset", dependencies=[Depends(_check_token)])
async def reset():
    INCIDENTS.clear()
    LINK["last_contact_at"] = None
    await push()
    return {"ok": True}


@app.post("/board/clear")
async def clear_board():
    """The ED team clears its own screen between patients. Only this screen forgets; every vehicle keeps its record,
    and a new call arrives in full."""
    INCIDENTS.clear()
    await push()
    return {"ok": True}


@app.post("/incidents/{incident_id}/acknowledgements")
async def acknowledge(incident_id: str, body: Acknowledgement):
    if body.status not in {"received", "cath_lab_activated"}:
        raise HTTPException(400, "status must be received or cath_lab_activated")
    if incident_id not in INCIDENTS:
        raise HTTPException(404, "unknown incident")
    ack = {"at": now(), "status": body.status, "note": body.note}
    INCIDENTS[incident_id].setdefault("acknowledgements", []).append(ack)
    await push()
    return ack


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    CLIENTS.add(ws)
    await ws.send_json(view())
    try:
        while True:
            if await ws.receive_text() == "ping":      # screen heartbeat -> stale-screen detection
                await ws.send_json({"type": "pong", "t": now()})
    except WebSocketDisconnect:
        CLIENTS.discard(ws)


class _Revalidated(StaticFiles):
    """The wall screen runs for days: every load revalidates (a cheap 304), so an update is never hidden by a cache."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", _Revalidated(directory=str(Path(__file__).parent / "web"), html=True), name="web")
