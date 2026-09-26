"""A spoken destination ("Good Sam") to one hospital on the county's list. The official name or id is matched as
written; anything else goes to the local model, which lists every listed id the words could name
(config/prompts/destination_match.md). Only exactly one listed id is a match: none, several (a brand shared by two
campuses, "Kaiser") or anything off the list is no match, and Herald keeps the heard words for the medic."""
from __future__ import annotations

import re
from typing import Optional

from ..config import load_text
from ..core.ports import TextModel
from .facilities import Facility


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'")).strip()


def exact(heard: str, options: list[Facility]) -> Optional[str]:
    """The facility whose official name or id is exactly what was said (case and punctuation aside)."""
    said = _norm(heard)
    return next((f.id for f in options if said in (_norm(f.name), _norm(f.id))), None)


class DestinationResolver:
    def __init__(self, model: Optional[TextModel]):
        self.model = model
        self.system = load_text("prompts/destination_match.md")

    def resolve(self, heard: str, options: list[Facility]) -> Optional[str]:
        found = exact(heard, options)
        if found or self.model is None or not options:
            return found
        ids = [f.id for f in options]
        listing = "\n".join(f"{f.id}: {f.name}" for f in options)
        data = self.model.chat_json(self.system, f"Heard: {heard}\n\nHospitals:\n{listing}",
                                    schema={"type": "object", "additionalProperties": False, "required": ["matches"],
                                            "properties": {"matches": {"type": "array", "maxItems": len(ids),
                                                                       "items": {"type": "string", "enum": ids}}}},
                                    max_tokens=60)
        said = data.get("matches") if isinstance(data, dict) else None
        picks = {m for m in said if m in ids} if isinstance(said, list) else set()
        return picks.pop() if len(picks) == 1 else None
