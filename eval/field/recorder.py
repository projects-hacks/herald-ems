"""The recording station for the field evaluation (docs/TASK_SPECS.md S8).

  ~/miniforge3/envs/zgx/bin/python -m uvicorn eval.field.recorder:app --host 127.0.0.1 --port 8103
  then open http://localhost:8103 (browsers allow the microphone only on localhost or https; VS Code and
  `ssh -L 8103:localhost:8103` both forward the port)

An evaluation tool, not part of Herald: it shows each speaker their cards, records 16 kHz mono WAV, and keeps the
manifest and consent log. It never calls a model. Protocol wording and limits: eval/field/protocol.yaml."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .cards import Card, assign, condition_order, load_cards
from .manifest import ConsentLog, Manifest, check_speaker, now

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SAMPLE_RATE = 16000


def to_16k_mono(raw: bytes) -> np.ndarray:
    """Any WAV the browser sends -> float32 mono at 16 kHz (linear resampling; the page already sends 16 kHz)."""
    audio, sr = sf.read(io.BytesIO(raw), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE and len(audio):
        t = np.arange(int(len(audio) * SAMPLE_RATE / sr)) * (sr / SAMPLE_RATE)
        audio = np.interp(t, np.arange(len(audio)), audio).astype(np.float32)
    return audio


class NewSpeaker(BaseModel):
    consent: bool = False


def create_app(cards_path: Path = ROOT / "eval" / "field_cards_v1.jsonl",
               manifest_path: Path = ROOT / "eval" / "field_v1.jsonl",
               audio_dir: Path = ROOT / "data" / "field_audio",
               protocol_path: Path = HERE / "protocol.yaml", root: Path = ROOT) -> FastAPI:
    protocol = yaml.safe_load(Path(protocol_path).read_text(encoding="utf-8"))
    conditions = [c["id"] for c in protocol["conditions"]]
    manifest, consent = Manifest(manifest_path), ConsentLog(audio_dir)
    app = FastAPI(title="Herald field recorder")
    state: dict = {}

    def cards() -> dict[str, Card]:
        if "cards" not in state:
            if not Path(cards_path).exists():
                raise HTTPException(503, f"no cards yet: {cards_path}")
            state["cards"] = load_cards(cards_path)
        return state["cards"]

    def speaker_or_404(code: str) -> dict:
        try:
            check_speaker(code)
        except ValueError as e:
            raise HTTPException(400, str(e))
        s = consent.get(code)
        if s is None:
            raise HTTPException(404, f"no consenting speaker {code}")
        return s

    def plan(s: dict) -> list[dict]:
        """This speaker's clips in recording order: one block per condition, the same cards in each block."""
        ids = assign(list(cards()), s["index"], protocol["cards_per_speaker"])
        done = manifest.done(s["speaker"])
        return [{"card": cards()[cid].view(), "condition": cond, "done": (cid, cond) in done}
                for cond in condition_order(conditions, s["index"]) for cid in ids]

    def relative(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(Path(root).resolve()))
        except ValueError:
            return str(p)

    @app.get("/")
    async def page():
        return FileResponse(HERE / "recorder.html", media_type="text/html")

    @app.get("/api/protocol")
    async def get_protocol():
        return protocol

    @app.get("/api/speakers")
    async def speakers():
        out = []
        for s in consent.speakers():
            p = plan(s)
            out.append({**s, "done": sum(x["done"] for x in p), "total": len(p)})
        return out

    @app.post("/api/speakers")
    async def new_speaker(body: NewSpeaker):
        if not body.consent:
            raise HTTPException(400, "recording needs the speaker's consent")
        cards()                                             # fail before creating a speaker if there are no cards
        s = consent.add(protocol["consent_version"])
        return {**s, "plan": plan(s)}

    @app.get("/api/speakers/{code}/plan")
    async def get_plan(code: str):
        s = speaker_or_404(code)
        return {**s, "plan": plan(s)}

    @app.delete("/api/speakers/{code}")
    async def withdraw(code: str):
        speaker_or_404(code)
        removed = manifest.remove_speaker(code)
        consent.withdraw(code)
        return {"speaker": code, "clips_deleted": removed}

    def clip_path(code: str, card: str, condition: str) -> Path:
        s = speaker_or_404(code)
        if condition not in conditions:
            raise HTTPException(400, f"condition must be one of {conditions}")
        if card not in assign(list(cards()), s["index"], protocol["cards_per_speaker"]):
            raise HTTPException(400, f"{card} is not one of {code}'s cards")
        return Path(audio_dir) / code / f"{card}_{condition}.wav"

    @app.post("/api/clips")
    async def save_clip(speaker: str = Form(...), card: str = Form(...), condition: str = Form(...),
                        file: UploadFile = File(...)):
        path = clip_path(speaker, card, condition)
        try:
            audio = to_16k_mono(await file.read())
        except Exception as e:
            raise HTTPException(400, f"send a WAV recording ({str(e)[:80]})")
        seconds = len(audio) / SAMPLE_RATE
        if not protocol["min_seconds"] <= seconds <= protocol["max_seconds"]:
            raise HTTPException(422, f"{seconds:.1f} s: a clip must be {protocol['min_seconds']}-"
                                     f"{protocol['max_seconds']} s")
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak < protocol["too_quiet_peak"]:
            raise HTTPException(422, "almost silent: check the microphone and record again")
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
        row = {"speaker": speaker, "card": card, "condition": condition, "file": relative(path),
               "seconds": round(seconds, 2), "peak": round(peak, 3), "recorded_at": now(),
               "capture": protocol["capture"]}
        manifest.upsert(row)
        return row

    @app.get("/api/clips/{code}/{card}/{condition}")
    async def get_clip(code: str, card: str, condition: str):
        path = clip_path(code, card, condition)
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="audio/wav")

    return app


app = create_app()
