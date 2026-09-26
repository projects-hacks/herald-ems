"""A spoken destination ("Good Sam") to one hospital on the county's list. The official name or id is matched as
written; anything else is the local model's choice among the listed ids, and "none" when it is not sure. The result
is only a suggestion: the medic confirms the destination with a tap."""
from __future__ import annotations

import re
from typing import Optional

from ..config import load_text
from ..core.ports import TextModel
from .facilities import Facility


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'")).strip()


class DestinationResolver:
    def __init__(self, model: Optional[TextModel]):
        self.model = model
        self.system = load_text("prompts/destination_match.md")

    def resolve(self, heard: str, options: list[Facility]) -> Optional[str]:
        said = _norm(heard)
        for f in options:
            if said in (_norm(f.name), _norm(f.id)):
                return f.id
        if self.model is None or not options:
            return None
        ids = [f.id for f in options]
        listing = "\n".join(f"{f.id}: {f.name}" for f in options)
        data = self.model.chat_json(self.system, f"Heard: {heard}\n\nHospitals:\n{listing}",
                                    schema={"type": "object", "additionalProperties": False, "required": ["id"],
                                            "properties": {"id": {"type": "string", "enum": [*ids, "none"]}}},
                                    max_tokens=20)
        choice = data.get("id")
        return choice if choice in ids else None
