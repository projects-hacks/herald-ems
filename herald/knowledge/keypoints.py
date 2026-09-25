"""Protocol key points: the local model picks which of the county's own sentences a paramedic needs for this
situation, and which exact phrases to mark. It only selects: every sentence shown is the county's text, and every
marked phrase is checked to be a verbatim part of its sentence, so nothing the model writes can reach the screen."""
from __future__ import annotations

import re
from typing import Optional

from ..config import load_text
from ..core.ports import TextModel

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["points"],
          "properties": {"points": {"type": "array", "maxItems": 3, "items": {
              "type": "object", "additionalProperties": False, "required": ["n", "mark"],
              "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 60},
                             "mark": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 80}}}}}}}
MAX_TOKENS = 160
MAX_SENTENCE = 260


def sentences(passage: dict) -> list[str]:
    """A passage's sentences, its section numbering dropped; lead-ins that end in a colon are not sentences."""
    body = re.sub(r"\s+", " ", passage["text"]).strip()
    body = re.sub(r"^[\d.]+[.)]?\s+|^[A-Z]\.\s+", "", body)
    parts = [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(“\"])", body)]
    return [s for s in parts if len(s) > 12 and not s.endswith(":")]


class KeyPointPicker:
    def __init__(self, model: TextModel):
        self.model = model
        self.system = load_text("prompts/protocol_keypoints.md")

    def pick(self, situation: str, passages: list[dict]) -> Optional[list[dict]]:
        """[{text, cite, marks}] best first, or None if the model could not be asked (the screen then falls back to
        each passage's lead sentence). An empty list means the model found nothing that applies."""
        numbered: list[tuple[str, str]] = []
        for p in passages:
            for s in sentences(p):
                numbered.append((s, f"{p['doc']} §{p['section']}"))
        if not numbered:
            return []
        body = "\n".join(f"[{i + 1}] ({cite}) {s[:MAX_SENTENCE]}" for i, (s, cite) in enumerate(numbered))
        data = self.model.chat_json(self.system, f"Situation: {situation}\n\nSentences:\n{body}", schema=SCHEMA,
                                    max_tokens=MAX_TOKENS)
        out, seen = [], set()
        for point in data.get("points", []):
            n = point.get("n")
            if not isinstance(n, int) or not 1 <= n <= len(numbered) or n in seen:
                continue                                   # an invented or repeated sentence number is ignored
            seen.add(n)
            text, cite = numbered[n - 1]
            marks = [m for m in point.get("mark", []) if isinstance(m, str) and len(m) > 1 and m in text]
            out.append({"text": text if len(text) <= MAX_SENTENCE else text[:MAX_SENTENCE].rsplit(" ", 1)[0] + " …",
                        "cite": cite, "marks": marks[:3]})
        return out
