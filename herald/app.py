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

from . import contract, extract_llm, extract_rules, llm, netem, pipeline, stt, trace, vision
from .guard import instruction_shaped
from .telemetry import TELEMETRY
from .relay import Relay
from .schema import KEYS, CapturedBy, FactIn, Role, Status, new_id, utcnow
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


def _ingest_batch(facts_in) -> list:
    facts = []
    for f in facts_in:
        try:
            facts.append(inc().ingest(f, record=False))
        except ValueError:
            continue
    inc().commit()
    return facts


async def _ingest_text(text: str, captured_by: CapturedBy, role: Optional[Role], speaker: Optional[str],
                       audio_id: Optional[str], use_llm: bool, stt_info: Optional[dict] = None) -> dict:
    """Two-phase: the rules result reaches the screen immediately; the local model's additions follow.
    Every step is recorded in the transcript entry's `trace` (the "Herald thinking" card)."""
    default_role = role or (Role.medic if captured_by == CapturedBy.medic else Role.family)
    import time as _t
    before = trace.summarize(inc().snapshot())
    t0 = _t.perf_counter()
    rules_in = extract_rules.extract(text, captured_by, default_role, speaker, audio_id)
    rules_ms = round((_t.perf_counter() - t0) * 1000, 1)
    facts = _ingest_batch(rules_in)
    after = trace.summarize(inc().snapshot())
    injected = instruction_shaped(text)
    llm_on = use_llm and llm.available() and not injected
    entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": text, "captured_by": captured_by.value,
             "speaker": speaker, "audio_id": audio_id, "fact_ids": [f.id for f in facts],
             "extract": {"rules": len(facts), "llm": None, "ms": rules_ms},
             "stt": stt_info,
             "trace": {"heard": {"text": text, "speaker": speaker or captured_by.value, "audio_id": audio_id,
                                 "stt": stt_info},
                       "rules": {"ms": rules_ms, "facts": [trace.fact_view(f) for f in facts]},
                       "model": ({"status": "running", "name": llm.model_name()} if llm_on else
                                 {"status": "skipped", "reason": f"instruction-shaped speech (\"{injected}\"): "
                                  "model output discarded for this utterance"} if injected else {"status": "off"}),
                       "guard": {"instruction_shaped": injected},
                       "effects": trace.diff(before, after)}}
    inc().transcripts.append(entry)
    await broadcast()
    if llm_on:
        asyncio.create_task(_refine_with_model(entry, text, captured_by, default_role, speaker, audio_id, rules_in))
    return {"transcript": entry, "facts": [f.model_dump(mode="json") for f in facts]}


async def _refine_with_model(entry: dict, text: str, captured_by: CapturedBy, default_role: Role,
                             speaker: Optional[str], audio_id: Optional[str], rules_in: list) -> None:
    import time as _t
    before = trace.summarize(inc().snapshot())
    t0 = _t.perf_counter()
    try:
        llm_in = await run_in_threadpool(extract_llm.extract, text, captured_by, default_role, speaker, audio_id)
        usage = getattr(extract_llm.extract, "last_usage", {}) or {}
        rules_by_key = {f.key: f for f in rules_in}
        agreed = sum(1 for f in llm_in if f.key in rules_by_key
                     and str(rules_by_key[f.key].value).lower() == str(f.value).lower())
        added = _ingest_batch(pipeline.merge_llm(rules_in, llm_in))
        entry["fact_ids"] += [f.id for f in added]
        entry["extract"]["llm"] = len(added)
        entry["trace"]["model"] = {"status": "done", "name": llm.model_name(),
                                   "ms": round((_t.perf_counter() - t0) * 1000),
                                   "tokens": usage.get("completion_tokens"), "proposed": len(llm_in),
                                   "facts": [trace.fact_view(f) for f in added],
                                   "agreed_with_rules": agreed,
                                   "overridden_by_rules": len(llm_in) - len(added) - agreed}
        after = trace.summarize(inc().snapshot())
        eff = trace.diff(before, after)
        for k in ("readiness", "alerts_new", "scores", "gaps_closed"):
            entry["trace"]["effects"][k] = entry["trace"]["effects"].get(k, []) + eff[k]
    except Exception as e:
        entry["trace"]["model"] = {"status": "error", "name": llm.model_name(), "error": str(e)[:200],
                                   "ms": round((_t.perf_counter() - t0) * 1000)}
    await broadcast()


@app.get("/api/telemetry")
async def telemetry():
    """Tokens, tok/s, GPU watts, energy, and $ vs a cloud equivalent, with the assumptions stated."""
    return await run_in_threadpool(TELEMETRY.snapshot, llm.model_name())


SERVICES = [
    {"name": "Deterministic scoring engine", "detail": "NEWS2, RACE, 2021 field triage; published tables, unit-tested"},
    {"name": "Gap-first alert checklists", "detail": "stroke / STEMI pre-alert readiness from county policy tables"},
    {"name": "Provenance and contradiction engine", "detail": "every fact linked to its audio or photo and speaker"},
    {"name": "Grounding validator", "detail": "model facts must be supported by what was said; ranges on photo readings"},
    {"name": "Weak-link relay", "detail": "prioritized, byte-budgeted, acknowledged updates of confirmed facts only"},
    {"name": "Synthetic evaluation harness", "detail": "gold sets, 3-run benchmarks with spread (eval/)"},
]


@app.get("/api/stack")
async def stack():
    """The AI stack in HP's console terms: models (with readiness) and intelligence services."""
    served = llm.model_name()
    models = [
        {"id": stt.MODEL, "role": "speech-to-text", "status": "ready" if stt._pipe is not None else "loading"},
        {"id": "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4", "served_as": "omni",
         "role": "speech-to-facts extraction and photo reading",
         "status": "ready" if served == "omni" else ("not served" if served is None else f"not served (serving {served})")},
    ]
    return {"models": models, "services": SERVICES,
            "summary": f"{len(models)} models · {len(SERVICES)} services", "cloud_ai_calls": 0}


@app.get("/api/meta")
async def meta():
    """Labels, units, relay tiers, change rules and checklists (the UI contract; see herald/contract.py)."""
    return contract.ui_contract()


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
    import time as _t
    t0 = _t.perf_counter()
    result = await run_in_threadpool(stt.transcribe, np.asarray(audio), sr, language)
    result["ms"] = round((_t.perf_counter() - t0) * 1000)
    if not result["text"]:
        return {"transcript": None, "facts": [], "stt": result}
    return await _ingest_text(result["text"], captured_by, None, speaker, audio_id, use_llm,
                              {"seconds": result["seconds"], "ms": result["ms"], "chunks": result["chunks"]})


@app.post("/api/photo")
async def post_photo(file: UploadFile = File(...), mode: str = Form("monitor")):
    """Phone camera -> local VLM -> unconfirmed facts with the photo as provenance."""
    raw = await file.read()
    photo_id = new_id("p")
    (PHOTO_DIR / f"{photo_id}.jpg").write_bytes(raw)
    import time as _t
    before = trace.summarize(inc().snapshot())
    t0 = _t.perf_counter()
    heard = {"text": f"photo ({mode.replace('_', ' ')})", "photo_id": photo_id}
    entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": f"[photo: {mode}]", "captured_by": "camera",
             "speaker": mode, "audio_id": None, "photo_id": photo_id, "fact_ids": [],
             "extract": {"rules": 0, "llm": 0, "ms": 0}}
    try:
        facts_in = await run_in_threadpool(vision.read_photo, raw, mode, photo_id)
    except Exception as e:
        # The photo is kept and the failure is recorded, so the NOW screen shows it (UX_PLAN §4.3 g).
        entry["trace"] = {"heard": heard, "rules": {"ms": 0, "facts": []},
                          "model": {"status": "error", "name": llm.model_name(), "error": str(e)[:200],
                                    "ms": round((_t.perf_counter() - t0) * 1000)},
                          "effects": trace.diff(before, before)}
        inc().transcripts.append(entry)
        await broadcast()
        raise HTTPException(503, f"vision model unavailable or failed: {str(e)[:200]}")
    ms = round((_t.perf_counter() - t0) * 1000)
    facts = _ingest_batch(facts_in)
    entry["fact_ids"] = [f.id for f in facts]
    entry["extract"] = {"rules": 0, "llm": len(facts), "ms": ms}
    entry["trace"] = {"heard": heard, "rules": {"ms": 0, "facts": []},
                      "model": {"status": "done", "name": llm.model_name(), "ms": ms,
                                "facts": [trace.fact_view(f) for f in facts]},
                      "effects": trace.diff(before, trace.summarize(inc().snapshot()))}
    inc().transcripts.append(entry)
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
    """Structured facts (the simulated monitor panel, or a device feed). One trace entry per call."""
    for f in facts:
        try:
            Incident.validate(f)
        except ValueError as e:
            raise HTTPException(400, str(e))
    before = trace.summarize(inc().snapshot())
    added = [inc().ingest(f, record=False) for f in facts]
    inc().commit()
    if added:
        speaker = added[0].speaker or added[0].captured_by.value
        said = " · ".join(f"{KEYS[f.key]['label']} {f.value}" for f in added)
        inc().transcripts.append({
            "id": new_id("t"), "ts": utcnow().isoformat(), "text": f"[{speaker}] {said}",
            "captured_by": added[0].captured_by.value, "speaker": speaker, "audio_id": None,
            "fact_ids": [f.id for f in added], "extract": {"rules": 0, "llm": None, "ms": 0},
            "trace": {"heard": {"text": said, "speaker": speaker, "source": "structured"},
                      "rules": {"ms": 0, "facts": [trace.fact_view(f) for f in added]},
                      "model": {"status": "off", "reason": "structured readings; nothing to extract"},
                      "guard": {"instruction_shaped": None},
                      "effects": trace.diff(before, trace.summarize(inc().snapshot()))}})
    await broadcast()
    return [f.model_dump(mode="json") for f in added]


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
            if await ws.receive_text() == "ping":      # client heartbeat -> stale-screen detection
                await ws.send_json({"type": "pong", "t": utcnow().isoformat()})
    except WebSocketDisconnect:
        CLIENTS.discard(ws)


@app.on_event("startup")
async def _startup():
    if os.getenv("HERALD_WARM_STT", "1") == "1":
        asyncio.get_event_loop().run_in_executor(None, stt.warm)
    asyncio.create_task(RELAY.run_forever(broadcast))
    TELEMETRY.start()


# The React build at / when it exists (HERALD_UI=classic switches back); the original screen stays at /classic/.
UI_DIST = ROOT / "ui" / "dist"
USE_NEW_UI = os.getenv("HERALD_UI", "new") == "new" and (UI_DIST / "index.html").exists()
app.mount("/classic", StaticFiles(directory=str(ROOT / "web"), html=True), name="classic")
app.mount("/", StaticFiles(directory=str(UI_DIST if USE_NEW_UI else ROOT / "web"), html=True), name="web")
