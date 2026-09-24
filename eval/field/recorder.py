"""The recording station for the field evaluation (docs/TASK_SPECS.md S8).

  ~/miniforge3/envs/zgx/bin/python -m eval.field.recorder --station <your name> --port 8105
  then open http://localhost:8105 (browsers allow the microphone only on localhost or https; VS Code and
  `ssh -L 8105:localhost:8105` both forward the port)

An evaluation tool, not part of Herald: it shows each speaker their cards, records 16 kHz mono WAV with the app's own
capture code (web/wav.js), and keeps the manifest and consent log. It never calls a model. Audio and the consent log
live in one folder shared by every clone on the Nano (eval/field/manifest.py), so speaker codes and card rotation are
the same whichever clone runs the station. Protocol wording and limits: eval/field/protocol.yaml."""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .cards import Card, assign, condition_order, load_cards
from .manifest import AUDIO_DIR, ConsentLog, Manifest, check_speaker, check_station, locked, now, station_of

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


def create_app(station: str, cards_path: Path = ROOT / "eval" / "field_cards_v1.jsonl",
               manifest_path: Path = ROOT / "eval" / "field_v1.jsonl", audio_dir: Path = AUDIO_DIR,
               protocol_path: Path = HERE / "protocol.yaml") -> FastAPI:
    station = check_station(station)
    audio_dir = Path(audio_dir)
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
        if station_of(code) != station:
            raise HTTPException(403, f"{code} was recorded at station {station_of(code)}: continue or withdraw "
                                     f"them there (their manifest lines live in that clone)")
        s = consent.get(code)
        if s is None:
            raise HTTPException(404, f"no consenting speaker {code}")
        return s

    def plan(s: dict) -> list[dict]:
        """This speaker's clips in recording order: one block per condition, the same cards in each block."""
        ids = assign(list(cards()), s["slot"], protocol["cards_per_speaker"])
        done = manifest.done(s["speaker"])
        return [{"card": cards()[cid].view(), "condition": cond, "done": (cid, cond) in done}
                for cond in condition_order(conditions, s["slot"]) for cid in ids]

    @app.get("/")
    async def page():
        return FileResponse(HERE / "recorder.html", media_type="text/html")

    @app.get("/wav.js")
    async def wav_js():
        """The app's own capture code (16 kHz resampling and WAV encoding), so field clips match what Herald sends."""
        return FileResponse(ROOT / "web" / "wav.js", media_type="text/javascript")

    @app.get("/api/protocol")
    async def get_protocol():
        return {**protocol, "station": station}

    @app.get("/api/speakers")
    async def speakers():
        out = []
        for s in consent.speakers(station):
            p = plan(s)
            out.append({**s, "done": sum(x["done"] for x in p), "total": len(p)})
        return out

    @app.post("/api/speakers")
    async def new_speaker(body: NewSpeaker):
        if not body.consent:
            raise HTTPException(400, "recording needs the speaker's consent")
        cards()                                             # fail before creating a speaker if there are no cards
        with locked(audio_dir):
            s = consent.add(protocol["consent_version"], station)
        return {**s, "plan": plan(s)}

    @app.get("/api/speakers/{code}/plan")
    async def get_plan(code: str):
        s = speaker_or_404(code)
        return {**s, "plan": plan(s)}

    @app.delete("/api/speakers/{code}")
    async def withdraw(code: str):
        speaker_or_404(code)
        with locked(audio_dir):
            try:
                consent.withdraw(code)
            except OSError as e:
                raise HTTPException(500, f"the recordings of {code} could not be deleted ({e}); nothing was marked "
                                         "withdrawn. Fix the cause and press Withdraw again.")
            removed = manifest.remove_speaker(code)         # after the audio is gone, so a failed delete keeps them
        return {"speaker": code, "clips_deleted": removed}

    def clip_path(code: str, card: str, condition: str) -> Path:
        s = speaker_or_404(code)
        if condition not in conditions:
            raise HTTPException(400, f"condition must be one of {conditions}")
        if card not in assign(list(cards()), s["slot"], protocol["cards_per_speaker"]):
            raise HTTPException(400, f"{card} is not one of {code}'s cards")
        return audio_dir / code / f"{card}_{condition}.wav"

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
        with locked(audio_dir):
            if consent.get(speaker) is None:                 # withdrawn while this clip was uploading
                raise HTTPException(404, f"no consenting speaker {speaker}")
            path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
            row = {"speaker": speaker, "card": card, "condition": condition,
                   "file": str(path.relative_to(audio_dir)), "seconds": round(seconds, 2), "peak": round(peak, 3),
                   "recorded_at": now(), "capture": protocol["capture"]}
            manifest.upsert(row)
        return row

    @app.get("/api/clips/{code}/{card}/{condition}")
    async def get_clip(code: str, card: str, condition: str):
        path = clip_path(code, card, condition)
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="audio/wav")

    return app


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Herald field recording station (docs/TASK_SPECS.md S8)")
    ap.add_argument("--station", required=True, help="who runs this station, e.g. jenil: speaker codes become jenil-s01")
    ap.add_argument("--port", type=int, default=8105, help="outside 8101-8104, the Herald dev servers (CONTRIBUTING.md)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--audio-dir", default=str(AUDIO_DIR), help="the shared recordings folder")
    ap.add_argument("--manifest", default=str(ROOT / "eval" / "field_v1.jsonl"))
    a = ap.parse_args(argv)
    import uvicorn
    uvicorn.run(create_app(a.station, manifest_path=Path(a.manifest), audio_dir=Path(a.audio_dir).expanduser()),
                host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
