"""The recordings manifest (eval/field_v1.jsonl) and the consent log (<audio dir>/consent.jsonl).

Manifest line: {"speaker", "card", "condition", "file", "seconds", "peak", "recorded_at", "capture"}. `file` is
relative to the repo root; the audio itself lives in data/field_audio/<speaker>/ (gitignored: voices are personal
data). Speakers are codes (s01, s02, ...), never names. A redo replaces the earlier clip of the same card and
condition, so the manifest has one line per (speaker, card, condition)."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SPEAKER_RE = re.compile(r"^s\d{2}$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """Atomic: a crash mid-write never leaves half a manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def check_speaker(code: str) -> str:
    if not SPEAKER_RE.match(code or ""):
        raise ValueError(f"speaker code must look like s01, got {code!r}")
    return code


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)

    def rows(self) -> list[dict]:
        return _read_jsonl(self.path)

    def upsert(self, row: dict) -> None:
        ident = (row["speaker"], row["card"], row["condition"])
        rows = [r for r in self.rows() if (r["speaker"], r["card"], r["condition"]) != ident]
        _write_jsonl(self.path, rows + [row])

    def remove_speaker(self, speaker: str) -> int:
        rows = self.rows()
        keep = [r for r in rows if r["speaker"] != speaker]
        _write_jsonl(self.path, keep)
        return len(rows) - len(keep)

    def done(self, speaker: str) -> set[tuple[str, str]]:
        return {(r["card"], r["condition"]) for r in self.rows() if r["speaker"] == speaker}


class ConsentLog:
    """Who agreed (by code), to which consent wording, when; and who withdrew. Kept next to the audio, not in git."""

    def __init__(self, audio_dir: Path):
        self.dir = Path(audio_dir)
        self.path = self.dir / "consent.jsonl"

    def entries(self) -> list[dict]:
        return _read_jsonl(self.path)

    def speakers(self) -> list[dict]:
        """Active speakers in the order they joined; `index` is fixed at joining and drives card assignment."""
        out: dict[str, dict] = {}
        for e in self.entries():
            if e["event"] == "consent":
                out[e["speaker"]] = {"speaker": e["speaker"], "index": e["index"], "consent_version": e["version"],
                                     "at": e["at"]}
            elif e["event"] == "withdrawn":
                out.pop(e["speaker"], None)
        return sorted(out.values(), key=lambda s: s["index"])

    def get(self, speaker: str) -> Optional[dict]:
        return next((s for s in self.speakers() if s["speaker"] == speaker), None)

    def add(self, version: str) -> dict:
        """A new speaker code. Indexes are never reused, even after a withdrawal, so assignments stay stable."""
        index = sum(1 for e in self.entries() if e["event"] == "consent")
        entry = {"event": "consent", "speaker": f"s{index + 1:02d}", "index": index, "version": version, "at": now()}
        _write_jsonl(self.path, self.entries() + [entry])
        return {"speaker": entry["speaker"], "index": index, "consent_version": version, "at": entry["at"]}

    def withdraw(self, speaker: str) -> None:
        """Deletes the speaker's audio and every derived line (transcripts, benchmark details) kept next to it; the
        log keeps only that the code withdrew."""
        check_speaker(speaker)
        shutil.rmtree(self.dir / speaker, ignore_errors=True)
        for path in self.dir.rglob("*.jsonl"):
            if path != self.path:
                rows = _read_jsonl(path)
                keep = [r for r in rows if r.get("speaker") != speaker]
                if len(keep) != len(rows):
                    _write_jsonl(path, keep)
        _write_jsonl(self.path, self.entries() + [{"event": "withdrawn", "speaker": speaker, "at": now()}])
