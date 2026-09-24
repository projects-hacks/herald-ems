"""Pick which retrieved passages answer the question, using the local general model. It only selects: the text
shown to the medic is always the county's own passage."""
from __future__ import annotations

from ..config import load_text
from ..core.ports import TextModel

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["best", "answerable"],
          "properties": {"best": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": 20}},
                         "answerable": {"type": "boolean"}}}


class LLMReranker:
    def __init__(self, model: TextModel, max_chars: int = 500):
        self.model, self.max_chars = model, max_chars
        self.system = load_text("prompts/protocol_rerank.md")

    def rerank(self, question: str, passages: list[dict]) -> tuple[list[int], bool]:
        """(indexes into `passages`, best first; answerable)."""
        body = "\n\n".join(f"[{i + 1}] {p['doc']} {p['section']} ({p.get('title') or ''}): "
                           f"{' > '.join(p.get('parents', [])[1:])}\n{p['text'][:self.max_chars]}"
                           for i, p in enumerate(passages))
        data = self.model.chat_json(self.system, f"Question: {question}\n\nPassages:\n{body}", schema=SCHEMA,
                                    max_tokens=40)
        best = [i - 1 for i in data.get("best", []) if isinstance(i, int) and 1 <= i <= len(passages)]
        return list(dict.fromkeys(best)), bool(data.get("answerable")) and bool(best)
