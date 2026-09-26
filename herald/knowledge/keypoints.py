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
MAX_RULE = 700          # a lead-in with its lettered list is one rule; it is offered and shown whole
ITEM = re.compile(r"^(?:(?:[a-z]|[ivx]{1,4}|\d{1,2})[.)]|\([a-z0-9]{1,3}\))\s+(?=[A-Z“\"(])")   # "a.", "ii)", "(3)" at a line start


def flow(text: str) -> str:
    """Rejoin the PDF's wrapped lines, keeping each lettered or numbered list item on its own line: the page's line
    breaks are layout, but its list structure is meaning ("shall be transported to: a. ...; and b. ...")."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in filter(None, lines):
        if out and not ITEM.match(ln):
            out[-1] += " " + ln
        else:
            out.append(ln)
    return "\n".join(out)


def _split(body: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(“\"])", body)]


def rules(passage: dict) -> list[dict]:
    """A passage as the units a paramedic can act on: {text, items}. A lead-in ending in a colon keeps its list, since
    "shall be transported to:" means nothing without what follows; other text is split into sentences. Section
    numbering is dropped; a bare lead-in whose list is not in the passage is not a rule."""
    head, *items = flow(passage["text"]).split("\n") or [""]
    head = re.sub(r"^[\d.]+[.)]?\s+|^[A-Z]\.\s+", "", head)
    out: list[dict] = []
    parts = _split(head)
    if items and parts and parts[-1].endswith(":"):
        *parts, lead = parts
        out_tail = [{"text": lead, "items": items}]
    else:
        out_tail = [{"text": t, "items": []} for item in items for t in _split(item)]
    out += [{"text": t, "items": []} for t in parts]
    return [r for r in out + out_tail if len(r["text"]) > 12 and (r["items"] or not r["text"].endswith(":"))]


def sentences(passage: dict) -> list[str]:
    """The passage's rules as plain text (a list rule reads lead-in then its items)."""
    return [" ".join([r["text"], *r["items"]]) for r in rules(passage)]


class KeyPointPicker:
    def __init__(self, model: TextModel):
        self.model = model
        self.system = load_text("prompts/protocol_keypoints.md")

    def pick(self, situation: str, passages: list[dict]) -> Optional[list[dict]]:
        """[{text, items, cite, marks}] best first, or None if the model could not be asked (the screen then falls back to
        each passage's lead sentence). An empty list means the model found nothing that applies."""
        numbered: list[tuple[dict, str]] = []
        for p in passages:
            for rule in rules(p):
                numbered.append((rule, f"{p['doc']} §{p['section']}"))
        if not numbered:
            return []
        body = "\n".join(f"[{i + 1}] ({cite}) {' '.join([r['text'], *r['items']])[:MAX_RULE if r['items'] else MAX_SENTENCE]}"
                         for i, (r, cite) in enumerate(numbered))
        data = self.model.chat_json(self.system, f"Situation: {situation}\n\nSentences:\n{body}", schema=SCHEMA,
                                    max_tokens=MAX_TOKENS)
        out, seen = [], set()
        for point in data.get("points", []):
            n = point.get("n")
            if not isinstance(n, int) or not 1 <= n <= len(numbered) or n in seen:
                continue                                   # an invented or repeated sentence number is ignored
            seen.add(n)
            rule, cite = numbered[n - 1]
            text, items = rule["text"], rule["items"]
            marks = [m for m in point.get("mark", []) if isinstance(m, str) and len(m) > 1 and any(m in t for t in [text, *items])]
            out.append({"text": text if items or len(text) <= MAX_SENTENCE else text[:MAX_SENTENCE].rsplit(" ", 1)[0] + " …",
                        "items": items, "cite": cite, "marks": marks[:3]})
        return out
