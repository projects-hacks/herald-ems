"""Model extractor: transcript -> typed facts with source role, from a local model (AGENTS.md invariant 1).

The model maps speech to the vocabulary. It never computes scores, never decides what is sent, and never gives
advice. Prompts and worked examples are content (config/prompts/). Output is validated against the vocabulary
and the grounding rules; anything invalid is dropped.

Two prompt styles:
- a general model (e.g. Nemotron-Omni) gets the full instructions, the key list, worked examples, and a strict
  JSON schema whose rows are exactly [key, value, who];
- a fine-tuned extractor (a profile in config/extraction.yaml, or a label listed in HERALD_FINETUNED_MODELS) gets
  exactly the input it was trained on: its short prompt, the speaker line from run D on, and JSON mode. Under the strict schema it appended an optional "?" to
  49 of 49 facts (2026-09-23 audit), and the "?" element also sent Omni into a degenerate mode (invented
  vitals, repeated keys to the token cap), so rows are exactly three elements.
"""
from __future__ import annotations

from typing import Optional

from ..config import load_jsonl, load_text
from ..core.confirmation import confidence_measure
from ..core.ports import TextModel
from ..core.schema import CapturedBy, FactIn, Provenance, Role
from ..core.vocabulary import Vocabulary, default_vocabulary
from .confidence import row_confidences
from .grounding import Grounding, default_grounding
from .profiles import Profiles

ROLE = {"m": Role.medic, "p": Role.patient, "f": Role.family, "b": Role.bystander}
SEX = {"female": "F", "woman": "F", "f": "F", "male": "M", "man": "M", "m": "M"}
MAX_TOKENS = 160


def output_schema(vocab: Vocabulary) -> dict:
    """Typed, bounded rows: an unbounded value type let the model ramble to max_tokens (audit 2026-09-23)."""
    return {
        "type": "object", "additionalProperties": False, "required": ["f"],
        "properties": {"f": {"type": "array", "maxItems": 16, "items": {
            "type": "array", "minItems": 3, "maxItems": 3,
            "prefixItems": [{"type": "string", "enum": list(vocab.keys)},
                            {"anyOf": [{"type": "number"}, {"type": "boolean"},
                                       {"type": "string", "maxLength": 48},
                                       {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 40}}]},
                            {"type": "string", "maxLength": 24}],
        }}},
    }


class Prompts:
    """The general-model prompt: instructions with the key list, and worked examples."""

    def __init__(self, system: str, examples: list[tuple[str, str]], vocab: Vocabulary):
        key_list = "; ".join(f"{k} [{v['type']}]" for k, v in vocab.keys.items())
        self.system = system.replace("{keys}", key_list)
        self.examples = examples

    @classmethod
    def from_config(cls, vocab: Vocabulary) -> "Prompts":
        return cls(load_text("prompts/extract_system.md"),
                   [(e["user"], e["assistant"]) for e in load_jsonl("prompts/extract_examples.jsonl")], vocab)


class ModelExtractor:
    """The `Extractor` interface over a local `TextModel`."""

    def __init__(self, model: TextModel, *, vocabulary: Optional[Vocabulary] = None,
                 grounding: Optional[Grounding] = None, prompts: Optional[Prompts] = None,
                 finetuned_labels: tuple[str, ...] = ("ems",), confidence_mode: Optional[str] = None):
        self.model = model
        self.vocab = vocabulary or default_vocabulary()
        self.grounding = grounding or default_grounding()
        self.prompts = prompts or Prompts.from_config(self.vocab)
        self.profiles = Profiles.from_config(finetuned_labels)
        self.schema = output_schema(self.vocab)
        self.last_usage: dict = {}
        measure, self.top_logprobs = confidence_measure()
        self.confidence_mode = confidence_mode or measure      # the calibrated measure (config/confirmation.yaml)

    @property
    def name(self) -> str:
        return f"llm:{self.model.model_name()}"

    def is_finetuned(self, label: Optional[str]) -> bool:
        return self.profiles.for_label(label) is not None

    def request_for(self, label: Optional[str]) -> tuple[str, Optional[list], Optional[dict]]:
        """(system prompt, worked examples, output schema) for the served model."""
        profile = self.profiles.for_label(label)
        if profile is not None:
            return profile.prompt, None, None
        return self.prompts.system, self.prompts.examples, self.schema

    def extract(self, text: str, captured_by: CapturedBy = CapturedBy.medic, default_role: Role = Role.medic,
                default_speaker: Optional[str] = None, audio_id: Optional[str] = None) -> list[FactIn]:
        usage: dict = {}
        label = self.model.model_name()
        system, examples, schema = self.request_for(label)
        user = self.profiles.model_input(self.profiles.for_label(label), text, captured_by, default_speaker)
        data = self.model.chat_json(system, user, schema=schema, max_tokens=MAX_TOKENS, usage=usage, examples=examples,
                                    logprobs=True,
                                    top_logprobs=self.top_logprobs if self.confidence_mode == "order_free" else 0)
        self.last_usage = usage
        rows = data.get("f", [])
        confs = (row_confidences(data.get("_content", ""), data.get("_tokens", []), self.confidence_mode)
                 if data.get("_tokens") else [])
        if len(confs) != len(rows):          # can't align (e.g. salvaged output): no auto-confirm for this utterance
            confs = [0.0] * len(rows)
        out: list[FactIn] = []
        for row, conf in zip(rows, confs):
            if (not isinstance(row, list) or len(row) < 3 or not isinstance(row[0], str)
                    or row[0] not in self.vocab or row[1] is None):
                continue
            key, value, who = row[0], row[1], str(row[2] or "m")
            if not self.grounding.supported(key, value, text):
                continue
            if key == "patient.sex" and isinstance(value, str):
                value = SEX.get(value.strip().lower(), value)
            code, _, relation = who.partition(":")
            role = ROLE.get(code[:1].lower(), default_role)
            if captured_by != CapturedBy.medic:
                # Someone else's mic: the words are that person's own. The model reads every utterance as the medic's,
                # so its `who` there can name the subject ("Mom is allergic…" -> "mother"; live test 2026-09-23).
                # A known speaker is the source; with none, the model's patient-vs-family call is kept
                # ("I don't take any blood thinners" -> patient).
                if default_speaker:
                    role, speaker = default_role, default_speaker
                else:
                    role, speaker = (Role.patient if role == Role.patient else default_role), None
            else:
                speaker = relation or (default_speaker if role == default_role else None)
            out.append(FactIn(key=key, value=value, role=role, speaker=speaker, captured_by=captured_by,
                              confidence=round(min(conf, 0.999), 4),
                              provenance=Provenance(audio_id=audio_id, text=text, extractor=f"llm:{label}")))
        return out
