"""Herald server: capture -> patient state -> live NOW screen (WebSocket).

Run:  python -m uvicorn herald.app:app --host 0.0.0.0 --port 8100
Open: http://localhost:8100  (use a forwarded port so the browser allows the mic)
"""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm, netem, pipeline, stt, vision
from .relay import Relay
from .schema import CapturedBy, FactIn, Role, Status, new_id, utcnow
from .state import Incident

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
PHOTO_DIR = ROOT / "data" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Herald", version="0.1.0")
STATE: dict[str, Incident] = {"incident": Incident(dispatch=os.getenv("HERALD_DISPATCH", "possible stroke"))}
CLIENTS: set[WebSocket] = set()


def inc() -> Incident:
    return STATE["incident"]


RELAY = Relay(inc)


def full_state() -> dict:
    snap = inc().snapshot()
    rs = RELAY.status()
    snap["relay"] = rs
    snap["ed_sync"] = rs["sync"]
    snap["netem"] = STATE.get("netem")
    return snap


async def broadcast() -> None:
    snap = full_state()
    for ws in list(CLIENTS):
        try:
            await ws.send_json({"type": "state", "state": snap})
        except Exception:
            CLIENTS.discard(ws)


class NewIncident(BaseModel):
    dispatch: Optional[str] = None


class Authorize(BaseModel):
    destination: str
    scope: str = "stroke pre-alert set"


class RelayConfig(BaseModel):
    ed_url: Optional[str] = None


class TranscriptIn(BaseModel):
    text: str
    captured_by: CapturedBy = CapturedBy.medic
    role: Optional[Role] = None
    speaker: Optional[str] = None
    use_llm: bool = True


async def _ingest_text(text: str, captured_by: CapturedBy, role: Optional[Role], speaker: Optional[str],
                       audio_id: Optional[str], use_llm: bool, stt_info: Optional[dict] = None) -> dict:
    default_role = role or (Role.medic if captured_by == CapturedBy.medic else Role.family)
    facts_in, info = await run_in_threadpool(pipeline.extract, text, captured_by, default_role,
                                             speaker, audio_id, use_llm)
    facts = []
    for f in facts_in:
        try:
            facts.append(inc().ingest(f, record=False))
        except ValueError:
            continue
    inc().commit()
    entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": text, "captured_by": captured_by.value,
             "speaker": speaker, "audio_id": audio_id, "fact_ids": [f.id for f in facts],
             "extract": info, "stt": stt_info}
    inc().transcripts.append(entry)
    await broadcast()
    return {"transcript": entry, "facts": [f.model_dump(mode="json") for f in facts]}


@app.get("/api/health")
async def health():
    return {"llm_model": llm.model_name(), "stt_model": stt.MODEL, "stt_loaded": stt._pipe is not None,
            "incident": inc().id, "cloud_ai_calls": 0}


@app.post("/api/incident")
async def new_incident(body: NewIncident):
    STATE["incident"] = Incident(dispatch=body.dispatch)
    RELAY.reset()
    await broadcast()
    return full_state()


@app.get("/api/state")
async def get_state():
    return full_state()


@app.post("/api/relay/authorize")
async def relay_authorize(body: Authorize):
    """The medic authorizes destination + scope once; in-scope updates then flow on their own."""
    RELAY.authorize(body.destination, body.scope)
    await broadcast()
    return RELAY.status()


@app.post("/api/relay/config")
async def relay_config(body: RelayConfig):
    RELAY.ed_url = body.ed_url
    await broadcast()
    return RELAY.status()


@app.post("/api/transcript")
async def post_transcript(body: TranscriptIn):
    return await _ingest_text(body.text, body.captured_by, body.role, body.speaker, None, body.use_llm)


@app.post("/api/audio")
async def post_audio(file: UploadFile = File(...), captured_by: CapturedBy = Form(CapturedBy.medic),
                     speaker: Optional[str] = Form(None), language: Optional[str] = Form(None),
                     use_llm: bool = Form(True)):
    raw = await file.read()
    try:
        audio, sr = sf.read(io.BytesIO(raw), dtype="float32")
    except Exception as e:
        raise HTTPException(400, f"send 16-bit PCM WAV audio ({e})")
    audio_id = new_id("a")
    sf.write(AUDIO_DIR / f"{audio_id}.wav", audio, sr)
    result = await run_in_threadpool(stt.transcribe, np.asarray(audio), sr, language)
    if not result["text"]:
        return {"transcript": None, "facts": [], "stt": result}
    return await _ingest_text(result["text"], captured_by, None, speaker, audio_id, use_llm,
                              {"seconds": result["seconds"], "chunks": result["chunks"]})


@app.post("/api/photo")
async def post_photo(file: UploadFile = File(...), mode: str = Form("monitor")):
    """Phone camera -> local VLM -> unconfirmed facts with the photo as provenance."""
    raw = await file.read()
    photo_id = new_id("p")
    (PHOTO_DIR / f"{photo_id}.jpg").write_bytes(raw)
    try:
        facts_in = await run_in_threadpool(vision.read_photo, raw, mode, photo_id)
    except Exception as e:
        raise HTTPException(503, f"vision model unavailable or failed: {str(e)[:200]}")
    facts = []
    for f in facts_in:
        try:
            facts.append(inc().ingest(f, record=False))
        except ValueError:
            continue
    inc().commit()
    inc().transcripts.append({"id": new_id("t"), "ts": utcnow().isoformat(), "text": f"[photo: {mode}]",
                              "captured_by": "camera", "speaker": mode, "audio_id": None, "photo_id": photo_id,
                              "fact_ids": [f.id for f in facts], "extract": {"rules": 0, "llm": len(facts), "ms": 0}})
    await broadcast()
    return {"photo_id": photo_id, "facts": [f.model_dump(mode="json") for f in facts]}


@app.get("/api/photo/{photo_id}")
async def get_photo(photo_id: str):
    p = PHOTO_DIR / f"{Path(photo_id).name}.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


@app.get("/api/audio/{audio_id}")
async def get_audio(audio_id: str):
    p = AUDIO_DIR / f"{Path(audio_id).name}.wav"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/wav")


@app.post("/api/facts")
async def post_facts(facts: list[FactIn]):
    out = []
    for f in facts:
        try:
            out.append(inc().ingest(f, record=False).model_dump(mode="json"))
        except ValueError as e:
            raise HTTPException(400, str(e))
    inc().commit()
    await broadcast()
    return out


@app.post("/api/facts/{fact_id}/{action}")
async def fact_action(fact_id: str, action: str):
    status = {"confirm": Status.confirmed, "reject": Status.rejected}.get(action)
    if status is None:
        raise HTTPException(400, "action must be confirm or reject")
    try:
        f = inc().set_status(fact_id, status)
    except KeyError:
        raise HTTPException(404)
    await broadcast()
    return f.model_dump(mode="json")


@app.post("/api/netem/{mode}")
async def netem_mode(mode: str):
    """Presenter control for the emulated link (Toxiproxy). Not part of the product."""
    if mode not in ("good", "weak", "down"):
        raise HTTPException(400, "mode must be good, weak, or down")
    try:
        proxy = await run_in_threadpool(netem.set_mode, mode)
    except Exception as e:
        raise HTTPException(503, f"toxiproxy not reachable: {e}")
    STATE["netem"] = mode
    await broadcast()
    return {"mode": mode, "enabled": proxy.get("enabled"), "toxics": [t["name"] for t in proxy.get("toxics", [])]}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    CLIENTS.add(ws)
    await ws.send_json({"type": "state", "state": full_state()})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        CLIENTS.discard(ws)


@app.on_event("startup")
async def _startup():
    if os.getenv("HERALD_WARM_STT", "1") == "1":
        asyncio.get_event_loop().run_in_executor(None, stt.warm)
    asyncio.create_task(RELAY.run_forever(broadcast))


app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")
