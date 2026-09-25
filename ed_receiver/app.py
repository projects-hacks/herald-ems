"""Mock emergency-department receiver. A plain HTTP service with no AI.

Run it on a DIFFERENT machine or network from the Nano (e.g., a teammate's laptop), so the
link between them can be degraded for real:
    python -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200
Idempotent by sequence number: a retried packet is acknowledged again but never applied twice.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Herald ED receiver")
INCIDENTS: dict[str, dict] = {}
CLIENTS: set[WebSocket] = set()
LINK = {"last_contact_at": None}   # any request from the ambulance (packet or idle probe)


class Acknowledgement(BaseModel):
    status: str
    note: str | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def view() -> dict:
    return {"incidents": INCIDENTS, "last_contact_at": LINK["last_contact_at"]}


async def push() -> None:
    for ws in list(CLIENTS):
        try:
            await ws.send_json(view())
        except Exception:
            CLIENTS.discard(ws)


@app.post("/ingest")
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
            inc["history"].setdefault(k, []).append({"v": v, "t": now()})
        inc["fields"][k] = {"v": v, "seq": p["q"], "t": now()}
    for key in p.get("rm", []):
        previous = inc["fields"].pop(key, None)
        inc["audit"].append({"at": now(), "action": "withdrawn", "key": key, "seq": p["q"],
                             "previous": previous["v"] if previous else None})
    if p.get("tl"):
        inc["timeline"] = p["tl"]
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


@app.post("/reset")
async def reset():
    INCIDENTS.clear()
    LINK["last_contact_at"] = None
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


app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "web"), html=True), name="web")
