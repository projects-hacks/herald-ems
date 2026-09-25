"""Capture endpoints: typed/replayed text, audio clips, photos, structured readings, and their evidence files."""
from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...core.incident import IncidentEnded
from ...core.schema import CapturedBy, FactIn, Role, new_id
from ..capture import ModelUnavailable
from . import get_capture, get_ctx

router = APIRouter(prefix="/api")


class TranscriptIn(BaseModel):
    text: str
    captured_by: CapturedBy = CapturedBy.medic
    role: Optional[Role] = None
    speaker: Optional[str] = None
    use_llm: bool = True


@router.post("/transcript")
async def post_transcript(body: TranscriptIn, cap=Depends(get_capture)):
    try:
        return await cap.text(body.text, body.captured_by, body.role, body.speaker, None, body.use_llm)
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except ModelUnavailable as e:
        raise HTTPException(503, str(e))


@router.post("/audio")
async def post_audio(file: UploadFile = File(...), captured_by: CapturedBy = Form(CapturedBy.medic),
                     speaker: Optional[str] = Form(None), language: Optional[str] = Form(None),
                     use_llm: bool = Form(True), c=Depends(get_ctx), cap=Depends(get_capture)):
    try:
        c.incident.ensure_open()
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    raw = await file.read()
    try:
        audio, sr = sf.read(io.BytesIO(raw), dtype="float32")
    except Exception as e:
        raise HTTPException(400, f"send 16-bit PCM WAV audio ({e})")
    audio_id = new_id("a")
    with c.incident.lock:
        try:
            c.incident.ensure_open()
        except IncidentEnded as e:
            raise HTTPException(409, str(e)) from None
        c.settings.audio_dir.mkdir(parents=True, exist_ok=True)
        sf.write(c.settings.audio_dir / f"{audio_id}.wav", audio, sr)
        c.incident.register_media("audio", audio_id)
    t0 = time.perf_counter()
    try:
        result = await run_in_threadpool(c.stt.transcribe, np.asarray(audio), sr, language)
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000)
        try:
            await cap.stt_failure(audio_id, captured_by, speaker, str(e), ms)
        except IncidentEnded as ended:
            raise HTTPException(409, str(ended)) from None
        raise HTTPException(503, "speech-to-text failed; recording kept for retry") from None
    result["ms"] = round((time.perf_counter() - t0) * 1000)
    if not result["text"]:
        try:
            c.incident.ensure_open()
        except IncidentEnded as e:
            raise HTTPException(409, str(e)) from None
        return {"transcript": None, "facts": [], "stt": result}
    try:
        return await cap.text(result["text"], captured_by, None, speaker, audio_id, use_llm,
                              {"seconds": result["seconds"], "ms": result["ms"], "chunks": result["chunks"]})
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except ModelUnavailable as e:
        raise HTTPException(503, str(e))


@router.post("/transcripts/{entry_id}/retry")
async def retry_transcript(entry_id: str, cap=Depends(get_capture)):
    try:
        return {"transcript": await cap.retry_text(entry_id)}
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except KeyError:
        raise HTTPException(404) from None
    except ModelUnavailable as e:
        raise HTTPException(503, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/photo")
async def post_photo(file: UploadFile = File(...), mode: str = Form("monitor"), cap=Depends(get_capture)):
    """Phone camera -> local VLM -> unconfirmed facts with the photo as provenance."""
    raw = await file.read()
    try:
        return await cap.photo(raw, mode)
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except Exception as e:
        raise HTTPException(503, f"vision model unavailable or failed: {str(e)[:200]}")


@router.post("/facts")
async def post_facts(facts: list[FactIn], cap=Depends(get_capture)):
    """Structured facts (the simulated monitor panel, or a device feed). One trace entry per call."""
    try:
        return await cap.structured(facts)
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e))


def _evidence(directory: Path, name: str, suffix: str, media_type: str) -> FileResponse:
    p = directory / f"{Path(name).name}{suffix}"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=media_type)


@router.get("/photo/{photo_id}")
async def get_photo(photo_id: str, c=Depends(get_ctx)):
    return _evidence(c.settings.photo_dir, photo_id, ".jpg", "image/jpeg")


@router.get("/audio/{audio_id}")
async def get_audio(audio_id: str, c=Depends(get_ctx)):
    return _evidence(c.settings.audio_dir, audio_id, ".wav", "audio/wav")
