"""Where the field evaluation keeps its data: the recordings manifest (eval/field_v1.jsonl) and, in one folder shared
by every clone on the Nano, the audio, the consent log and everything derived from the audio.

Speaker codes are `<station>-s<NN>` (jenil-s01): the station is the person running the recorder, so two stations
never mint the same code. A speaker's slot decides which cards they say and which condition comes first; slots are
global (the consent log is shared), so the card blocks stay balanced however many stations record.

Manifest line: {"speaker", "card", "condition", "file", "seconds", "peak", "recorded_at", "capture"}. `file` is
relative to the shared audio folder. A redo replaces the earlier clip of the same card and condition, so the manifest
has one line per (speaker, card, condition). Speakers are codes, never names."""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

AUDIO_DIR = Path.home() / "herald-field-audio"       # outside every clone: one set of recordings for the whole team
STATION_RE = re.compile(r"^[a-z][a-z0-9]{1,15}$")
SPEAKER_RE = re.compile(r"^([a-z][a-z0-9]{1,15})-s(\d{2,})$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict]:
    """Blank lines are skipped, so a hand-edited file with an extra newline still loads."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Atomic: a crash mid-write never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def check_station(station: str) -> str:
    if not STATION_RE.match(station or ""):
        raise ValueError(f"station must be a short lowercase name such as jenil, got {station!r}")
    return station


def check_speaker(code: str) -> str:
    if not SPEAKER_RE.match(code or ""):
        raise ValueError(f"speaker code must look like jenil-s01, got {code!r}")
    return code


def station_of(code: str) -> str:
    return check_speaker(code).rsplit("-s", 1)[0]


@contextmanager
def locked(audio_dir: Path) -> Iterator[None]:
    """One writer at a time across every station on the machine (the consent log and the audio folder are shared)."""
    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    with open(audio_dir / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)

    def rows(self) -> list[dict]:
        return read_jsonl(self.path)

    def upsert(self, row: dict) -> None:
        ident = (row["speaker"], row["card"], row["condition"])
        rows = [r for r in self.rows() if (r["speaker"], r["card"], r["condition"]) != ident]
        write_jsonl(self.path, rows + [row])

    def remove_speaker(self, speaker: str) -> int:
        rows = self.rows()
        keep = [r for r in rows if r["speaker"] != speaker]
        write_jsonl(self.path, keep)
        return len(rows) - len(keep)

    def done(self, speaker: str) -> set[tuple[str, str]]:
        return {(r["card"], r["condition"]) for r in self.rows() if r["speaker"] == speaker}


def scrub(path: Path, speaker: str) -> int:
    """Drop every line of a JSONL file that belongs to `speaker`. A line that doesn't parse (a hand-edited file) is
    dropped too if it mentions the code, and kept otherwise, so one bad line never stops a withdrawal."""
    lines = path.read_text(encoding="utf-8").splitlines()
    keep = []
    for line in lines:
        try:
            mine = json.loads(line).get("speaker") == speaker if line.strip() else False
        except (ValueError, AttributeError):
            mine = f'"{speaker}"' in line
        if not mine:
            keep.append(line)
    if len(keep) != len(lines):
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(line + "\n" for line in keep))
        os.replace(tmp, path)
    return len(lines) - len(keep)


class ConsentLog:
    """Who agreed (by code), to which consent wording, when, with which slot; and who withdrew. Kept in the shared
    audio folder, not in git. Callers hold `locked(audio_dir)` around `add` and `withdraw`."""

    def __init__(self, audio_dir: Path):
        self.dir = Path(audio_dir)
        self.path = self.dir / "consent.jsonl"

    def entries(self) -> list[dict]:
        return read_jsonl(self.path)

    def speakers(self, station: Optional[str] = None) -> list[dict]:
        """Active speakers in the order they joined (all stations, or one). `slot` is fixed at joining."""
        out: dict[str, dict] = {}
        for e in self.entries():
            if e["event"] == "consent":
                out[e["speaker"]] = {"speaker": e["speaker"], "station": e["station"], "slot": e["slot"],
                                     "consent_version": e["version"], "at": e["at"]}
            elif e["event"] == "withdrawn":
                out.pop(e["speaker"], None)
        return [s for s in out.values() if station is None or s["station"] == station]

    def get(self, speaker: str) -> Optional[dict]:
        return next((s for s in self.speakers() if s["speaker"] == speaker), None)

    def add(self, version: str, station: str) -> dict:
        """A new speaker. The code counts this station's consents, so it is never reused, even after a withdrawal.
        The slot is the lowest one no active speaker holds, at any station: a withdrawn speaker's cards go to the
        next person instead of being left unrecorded."""
        check_station(station)
        entries = self.entries()
        n = 1 + sum(1 for e in entries if e["event"] == "consent" and e["station"] == station)
        held = {s["slot"] for s in self.speakers()}
        slot = next(k for k in range(len(held) + 1) if k not in held)
        entry = {"event": "consent", "speaker": f"{station}-s{n:02d}", "station": station, "slot": slot,
                 "version": version, "at": now()}
        write_jsonl(self.path, entries + [entry])
        return {"speaker": entry["speaker"], "station": station, "slot": slot, "consent_version": version,
                "at": entry["at"]}

    def withdraw(self, speaker: str) -> None:
        """Deletes every derived line (transcripts, benchmark details, review files) first, then the audio, and
        logs the withdrawal only once the audio is verifiably gone. Any failure raises before anything is logged,
        so the speaker stays listed and the withdrawal can be retried."""
        check_speaker(speaker)
        for path in sorted(self.dir.rglob("*.jsonl")):
            if path != self.path:
                scrub(path, speaker)
        folder = self.dir / speaker
        if folder.exists():
            shutil.rmtree(folder)
        if folder.exists():
            raise OSError(f"could not delete {folder}")
        write_jsonl(self.path, self.entries() + [{"event": "withdrawn", "speaker": speaker, "at": now()}])
