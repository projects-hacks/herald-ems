"""The check step of speech: the extraction model proposes facts from what was said (the medic's report or words the
room microphone caught); a second local model reads the same words and keeps only the facts those words actually state about the patient. What
it rejects is discarded before it reaches the record (kept in the trace for audit, never on the screen). The prompt is
content (config/prompts/fact_verify.md); the model only answers keep or discard for facts it was shown, so it can
remove a proposal but never add or change one."""
from __future__ import annotations

import json
from typing import Optional

from ..config import load_text
from ..core.ports import TextModel
from ..core.schema import FactIn

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["facts"],
          "properties": {"facts": {"type": "array", "maxItems": 40, "items": {
              "type": "object", "additionalProperties": False, "required": ["n", "keep", "why"],
              "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 40},
                             "keep": {"type": "boolean"},
                             "why": {"type": "string"}}}}}}
# No maxLength on `why`: a reason cut at the limit by the grammar left the model emitting whitespace until max_tokens,
# and the answer could not be parsed (2 of 100 medic reports, 2026-09-26). The prompt asks for a few words; the code
# keeps 80 characters.
MAX_TOKENS = 400
TOKENS_PER_FACT = 48      # one verdict with a few-word why; a medic's full report can carry a dozen facts


def schema_for(n: int) -> dict:
    """Exactly one verdict per proposed fact: an empty answer would otherwise read as "keep everything"."""
    s = json.loads(json.dumps(SCHEMA))
    s["properties"]["facts"].update({"minItems": n, "maxItems": n})
    s["properties"]["facts"]["items"]["properties"]["n"]["maximum"] = n
    return s


class FactVerifier:
    def __init__(self, model: TextModel):
        self.model = model
        self.system = load_text("prompts/fact_verify.md")

    def check(self, words: str, facts: list[FactIn], dispatch: Optional[str] = None) -> tuple[list[FactIn], list[dict]]:   # noqa: ARG002
        """(kept, discarded). A fact the model did not answer for is kept (it stays unconfirmed and needs a tap);
        if the model cannot be asked at all, the caller keeps every fact and records why."""
        if not facts:
            return [], []
        listed = "\n".join(f"[{i + 1}] {f.key} = {json.dumps(f.value, ensure_ascii=False)}" for i, f in enumerate(facts))
        # the words alone: given the dispatch ("fall"), the model kept a "fall" complaint that the words never said
        user = f"Overheard words: \"{words}\"\n\nProposed facts:\n{listed}"
        data = self.model.chat_json(self.system, user, schema=schema_for(len(facts)),
                                    max_tokens=max(MAX_TOKENS, 64 + TOKENS_PER_FACT * len(facts)))
        verdict = {a["n"]: a for a in data.get("facts", []) if isinstance(a.get("n"), int)}
        kept, discarded = [], []
        for i, f in enumerate(facts, start=1):
            a = verdict.get(i)
            if a is not None and a.get("keep") is False:
                discarded.append({"key": f.key, "value": f.value, "why": str(a.get("why", ""))[:80]})
            else:
                kept.append(f)
        return kept, discarded
