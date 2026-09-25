"""Call-scoped evidence disposal.

Only generated IDs attached to the active incident are considered. No directory scan or
caller-supplied path participates in deletion.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.schema import utcnow

_ID = {"audio": re.compile(r"^a_[0-9a-f]{10}$"), "photo": re.compile(r"^p_[0-9a-f]{10}$")}
_SUFFIX = {"audio": ".wav", "photo": ".jpg"}


def _referenced(incident) -> dict[str, set[str]]:
    ids = {kind: set(values) for kind, values in incident.media_ids.items()}
    for entry in incident.transcripts:
        if entry.get("audio_id"):
            ids["audio"].add(entry["audio_id"])
        if entry.get("photo_id"):
            ids["photo"].add(entry["photo_id"])
    for fact in incident.facts:
        if fact.provenance.audio_id:
            ids["audio"].add(fact.provenance.audio_id)
        if fact.provenance.photo_id:
            ids["photo"].add(fact.provenance.photo_id)
    return ids


def dispose_incident_media(incident, *, audio_dir: Path, photo_dir: Path) -> dict:
    """End one call and unlink only its registered audio/photos. Repeated calls are idempotent."""
    with incident.lock:
        if incident.media_disposal is not None:
            return incident.media_disposal
        incident.ended_at = utcnow()
        directories = {"audio": audio_dir, "photo": photo_dir}
        deleted = {"audio": [], "photo": []}
        missing = {"audio": [], "photo": []}
        invalid = {"audio": [], "photo": []}
        for kind, ids in _referenced(incident).items():
            for media_id in sorted(ids):
                if not _ID[kind].fullmatch(media_id):
                    invalid[kind].append(media_id)
                    continue
                path = directories[kind] / f"{media_id}{_SUFFIX[kind]}"
                try:
                    path.unlink()
                    deleted[kind].append(media_id)
                except FileNotFoundError:
                    missing[kind].append(media_id)
        incident.media_disposal = {
            "at": incident.ended_at.isoformat(), "deleted": deleted, "missing": missing, "invalid": invalid,
        }
        return incident.media_disposal
