"""S9 wire boundary: bounded JPEG input, capture controls, and explicit mismatch resolution."""
from __future__ import annotations

import time
from urllib.parse import urlparse
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from ...capture.frames import decode_frame
from ...capture.types import ROI
from ...core.schema import utcnow, new_id
from . import get_ctx, get_hub

router = APIRouter()


class PatientIn(BaseModel):
    incident_id: str | None = None


def check_patient(c, expected):
    if expected is not None and expected != c.incident.id:
        raise HTTPException(409, "patient changed; review before retrying")


class AutoIn(PatientIn):
    on: bool


class RoiIn(PatientIn):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x0: float
    y0: float
    x1: float
    y1: float
    target: Literal["monitor"] = "monitor"


class NowIn(PatientIn):
    mode: Literal["monitor", "pill_bottle", "form", "scene"] | None = None


class ResolveIn(BaseModel):
    action: Literal["keep", "edit"]
    value: dict | None = None


@router.get("/api/capture/status")
async def status(c=Depends(get_ctx)):
    c.capture_agent.patient_changed()
    return c.capture_agent.status()


@router.post("/api/capture/auto")
async def automatic(body: AutoIn, c=Depends(get_ctx), h=Depends(get_hub)):
    check_patient(c, body.incident_id)
    if body.on and c.capture_agent.source == "off":
        c.capture_agent.source = "browser"
    c.capture_agent.set_auto(body.on)
    await h.broadcast()
    return c.capture_agent.status()


@router.post("/api/capture/roi")
async def set_roi(body: RoiIn, c=Depends(get_ctx), h=Depends(get_hub)):
    check_patient(c, body.incident_id)
    try:
        c.capture_agent.set_roi(ROI(body.x0, body.y0, body.x1, body.y1))
    except ValueError as e:
        raise HTTPException(422, str(e))
    await h.broadcast()
    return c.capture_agent.status()


@router.delete("/api/capture/roi")
async def clear_roi(incident_id: str | None = None, c=Depends(get_ctx), h=Depends(get_hub)):
    check_patient(c, incident_id)
    c.capture_agent.set_roi(None)
    await h.broadcast()
    return c.capture_agent.status()


@router.post("/api/capture/now", status_code=202)
async def show(body: NowIn, c=Depends(get_ctx), h=Depends(get_hub)):
    check_patient(c, body.incident_id)
    c.capture_agent.manual(body.mode)
    await c.capture_agent.step()
    await h.broadcast()
    return c.capture_agent.status()


@router.post("/api/capture/verify/{fact_id}")
async def resolve(fact_id: str, body: ResolveIn, c=Depends(get_ctx), h=Depends(get_hub)):
    if body.action == "edit" and body.value is None:
        raise HTTPException(422, "edit requires the complete corrected dose record")
    try:
        fact = c.incident.resolve_verification(fact_id, body.value if body.action == "edit" else None)
    except KeyError:
        raise HTTPException(404, "dose not found in this incident")
    except ValueError as e:
        raise HTTPException(409, str(e))
    c.incident.transcripts.append({"id": new_id("t"), "ts": utcnow().isoformat(),
        "text": f"Medic {body.action} decision for label check on {fact_id}", "captured_by": "medic",
        "speaker": "medic verification", "audio_id": None, "fact_ids": [fact.id],
        "extract": {"rules": 0, "llm": None, "ms": 0},
        "trace": {"heard": {"text": f"Label check {body.action}: {fact_id}", "source": "structured"},
                  "rules": {"ms": 0, "facts": [c.tracer.fact_view(fact)]}, "model": {"status": "off"},
                  "effects": {"readiness": [], "alerts_new": [], "scores": [], "gaps_closed": []}}})
    await h.broadcast()
    return c.incident.projector.fact_view(fact)


@router.websocket("/ws/frames")
async def frames(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and urlparse(origin).netloc != ws.headers.get("host"):
        await ws.close(code=1008, reason="same-origin camera required")
        return
    ctx = ws.app.state.ctx
    agent = ctx.capture_agent
    if agent.source.startswith("replay:"):
        await ws.close(code=1008, reason="replay source owns capture")
        return
    # One camera owns the frame stream per incident; mixed camera views cannot share an ROI safely.
    if ctx.extra.get("frame_socket") is not None:
        await ws.close(code=1008, reason="another capture camera is connected")
        return
    await ws.accept()
    ctx.extra["frame_socket"] = ws
    owner = ctx.incident.id
    last = float("-inf")
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            if ctx.incident.id != owner:
                await ws.close(code=1008, reason="patient changed; reconnect explicitly")
                break
            raw = message.get("bytes")
            now = time.time()
            if now - last < 1 / agent.config["fps_in"]:
                # Answer every frame: the page sends the next one only after a reply, and one dropped in silence
                # (a frame a few ms early over a jittery link) read as a dead camera after 10 s and restarted it.
                await ws.send_json({"accepted": False, "gate": None, "throttled": True})
                continue
            last = now
            try:
                if raw is None:
                    raise ValueError("binary JPEG required")
                if not agent.auto and not agent.pending:
                    await ws.send_json({"accepted": False, "gate": None})
                    continue
                frame = decode_frame(raw, now, "browser", agent.config)
                result = agent.receive(frame)
                await agent.step()
                await ws.send_json({"accepted": result is not None, "gate": asdict(result) if result else None})
            except (ValueError, OSError) as e:
                await ws.send_json({"accepted": False, "gate": None, "error": str(e)[:160]})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if ctx.extra.get("frame_socket") is ws:
            ctx.extra.pop("frame_socket", None)
            if agent.auto:
                agent.set_auto(False)
            else:
                # A deliberately submitted manual still may finish after its camera closes.
                agent.buffer.clear(); agent.monitor_buffer.clear(); agent.pending.clear()
            await ws.app.state.hub.broadcast()
