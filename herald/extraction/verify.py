"""The check step of speech: the extraction model proposes facts from what was said (the medic's report or words the
room microphone caught); a second local model reads the same words and keeps only the facts those words actually state about the patient. What
it rejects is discarded before it reaches the record (kept in the trace for audit, never on the screen). The prompt is
content (config/prompts/fact_verify.md); the model only answers keep or discard for facts it was shown, so it can
remove a proposal but never add or change one.

The same read also answers two questions the words can answer and a voice cannot: whose information each fact is
(`said_by`: the medic's own report, the patient, or who the speaker is to the patient, "husband"), and the patient's
name when the words state it. The room microphone cannot tell voices apart, so this is how Herald knows who told it
what. The name is only ever a proposal for the medic's tap (vocabulary `require_tap`), and it must appear in the words."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..config import load_text
from ..core.ports import TextModel
from ..core.schema import FactIn
from ..core.vocabulary import Vocabulary, default_vocabulary

# No maxLength on `why`: a reason cut at the limit by the grammar left the model emitting whitespace until max_tokens,
# and the answer could not be parsed (2 of 100 medic reports, 2026-09-26). The prompt asks for a few words; the code
# keeps 80 characters. `said_by` comes before `why` and the name before the facts, so every string the model writes is
# followed by exactly one thing the grammar allows: with `said_by` after `why` the model stalled in whitespace there.
MAX_TOKENS = 400
TOKENS_PER_FACT = 56      # one verdict, who said it and a few-word why; a medic's full report can carry a dozen facts
MEDIC, PATIENT, UNCLEAR = "medic", "patient", "unclear"
MAX_NAME_WORDS = 4
# The name as the grammar allows it: empty, or up to four capitalised words. Unconstrained, the model once wrote a
# 400-token sentence into the name for words that named nobody ("none of the above, not a patient name, ...").
NAME_PATTERN = r"^([A-Z][A-Za-z'.-]{0,24}( [A-Z][A-Za-z'.-]{0,24}){0,%d})?$" % (MAX_NAME_WORDS - 1)


def said_by_choices(vocab: Vocabulary) -> list[str]:
    """What `said_by` may be: the medic, the patient, a word for who someone is to the patient, or unclear."""
    return [MEDIC, PATIENT, *vocab.speaker_words(), UNCLEAR]


def schema_for(n: int, said_by: Optional[list[str]] = None) -> dict:
    """Exactly one verdict per proposed fact: an empty answer would otherwise read as "keep everything". With no
    facts the model is asked only for the name (an empty array of verdicts is not a schema the server accepts)."""
    props: dict = {"patient_name": {"type": "string", "pattern": NAME_PATTERN}}
    if n:
        item = {"n": {"type": "integer", "minimum": 1, "maximum": n}, "keep": {"type": "boolean"}}
        if said_by:
            item["said_by"] = {"type": "string", "enum": said_by}
        item["why"] = {"type": "string"}
        props["facts"] = {"type": "array", "minItems": n, "maxItems": n, "items": {
            "type": "object", "additionalProperties": False, "required": list(item), "properties": item}}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


@dataclass
class CheckResult:
    kept: list[FactIn]
    discarded: list[dict]
    patient_name: Optional[str] = None     # the patient's name, as the words say it; None when they don't
    said_by: dict[int, str] = field(default_factory=dict)   # fact number (1-based) -> the model's answer


class FactVerifier:
    def __init__(self, model: TextModel, vocab: Optional[Vocabulary] = None):
        self.model = model
        self.system = load_text("prompts/fact_verify.md")
        self.said_by = said_by_choices(vocab or default_vocabulary())

    def model_label(self) -> str:
        name = getattr(self.model, "model_name", None)
        return (name() if callable(name) else None) or "check"

    def check(self, words: str, facts: list[FactIn], dispatch: Optional[str] = None) -> tuple[list[FactIn], list[dict]]:
        """(kept, discarded) of the proposed facts; see `read`."""
        if not facts:
            return [], []
        r = self.read(words, facts, dispatch)
        return r.kept, r.discarded

    def read(self, words: str, facts: list[FactIn], dispatch: Optional[str] = None) -> CheckResult:   # noqa: ARG002
        """Keep or discard each proposal, say whose information each kept one is (`provenance.heard_as`), and pick
        out the patient's name. A fact the model did not answer for is kept (it stays unconfirmed and needs a tap);
        if the model cannot be asked at all, the exception reaches the caller, which keeps every fact and says why."""
        listed = "\n".join(f"[{i + 1}] {f.key} = {json.dumps(f.value, ensure_ascii=False)}" for i, f in enumerate(facts))
        # the words alone: given the dispatch ("fall"), the model kept a "fall" complaint that the words never said
        user = f"Overheard words: \"{words}\"\n\nProposed facts:\n{listed or '(none)'}"
        data = self.model.chat_json(self.system, user, schema=schema_for(len(facts), self.said_by),
                                    max_tokens=max(MAX_TOKENS, 64 + TOKENS_PER_FACT * len(facts)))
        verdict = {a["n"]: a for a in data.get("facts", []) if isinstance(a.get("n"), int)}
        result = CheckResult([], [], self._name(data.get("patient_name"), words))
        for i, f in enumerate(facts, start=1):
            a = verdict.get(i)
            if a is not None and a.get("keep") is False:
                result.discarded.append({"key": f.key, "value": f.value, "why": str(a.get("why", ""))[:80]})
                continue
            if a is not None and a.get("keep") is True and f.provenance is not None:
                f.provenance.checked = True     # an explicit keep; an unanswered fact is kept but not checked
                who = a.get("said_by")
                if who in self.said_by and who != UNCLEAR:
                    f.provenance.heard_as = who
                    result.said_by[i] = who
            result.kept.append(f)
        return result

    @staticmethod
    def _name(name, words: str) -> Optional[str]:
        """The model's name for the patient, only if those words are in what was said: it reads a name, never
        invents one."""
        name = " ".join(str(name or "").split())
        # a name is a few words; a whole clause here is the model copying the sentence, not reading a name
        if not name or not _norm(name) or len(name.split()) > MAX_NAME_WORDS or f" {_norm(name)} " not in f" {_norm(words)} ":
            return None
        return name
