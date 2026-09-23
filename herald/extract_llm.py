"""LLM extractor: transcript -> typed facts with source role. Local model only.

The model maps speech to our schema. It never computes scores, never decides
what is sent, and never gives advice. Output is validated against KEYS; anything
invalid is dropped, and the rules extractor still runs as the safety net.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from . import llm

from .schema import KEYS, CapturedBy, FactIn, Provenance, Role

SYSTEM = """You convert a paramedic's spoken words into structured facts for an EMS record.
Return ONLY JSON: {"f": [[key, value, who], ...]} with one short array per fact and nothing else.
who = "m" if the medic observed/measured it or said it without attribution; "p" if the patient said it;
"f:<relation>" if a family member or caregiver said it (e.g. "f:husband", "f:facility nurse"); "b" if a bystander said it.
Attribution applies only to the clause after "<person> says/states/reports/denies"; a new clause is the medic's again.
patient.sex is "F" or "M".
Rules:
- Use only these keys (type in brackets): {keys}
- Only facts explicitly stated in THIS utterance. Never infer, never diagnose, never add treatment. The worked examples
  only show the format: never copy a value from them.
- Never add a vital sign that was not said (no assumed normal temperature). "D-stick", "sugar", "BGL" are glucose.
- After a spoken correction ("correction", "I mean", "sorry", "scratch that", "no wait"), give only the corrected value.
- Planned or future actions ("I'll attach the 12-lead", "we'll check a sugar") and questions are not facts. Hedged
  statements ("maybe", "I think", "not sure") are not facts.
- Blood pressure "148 over 92" -> vitals.sbp 148 and vitals.dbp 92. Temperatures in Fahrenheit -> convert to Celsius, one decimal.
- vitals.consciousness is one letter: A (alert), C (new confusion), V (responds to voice), P (responds to pain), U (unresponsive).
- RACE items only when that exam finding is described: exam.race.facial 0 none/1 mild/2 moderate-severe; exam.race.arm and
  exam.race.leg 0 normal/1 drift or holds <10 s/2 cannot lift against gravity; exam.race.gaze 0/1;
  exam.race.aphasia_agnosia 0 none/1 one of arm or deficit not recognized/2 neither recognized or severe aphasia.
  Score only a severity the words support. Findings stated as normal ("no droop", "no drift", "eyes midline", "speech is clear") are 0. Vague deficits without an
  exam ("weakness on the right", "slurred") go in stroke.deficits only, with no RACE items.
- symptom.onset = when the current symptoms started, for any complaint ("started 40 minutes ago", "since yesterday",
  "for three days"). stroke.lkw = the last time a possible-stroke patient was known normal ("fine at 1:40"). Times as spoken.
- meds.list = the patient's own home medications, as lowercase generic names (a brand name or misheard brand becomes
  its generic). Drugs EMS gives now are not meds.list. A drug class without a drug name is not a med.
- meds.anticoagulant = an anticoagulant the patient takes (generic, lowercase), or "none" for "no blood thinners".
  Antiplatelets such as clopidogrel or aspirin are not anticoagulants. "no known allergies" -> allergies [].
- stroke.onset_witnessed and stroke.deficits only for stroke-like symptoms, not for trauma or a found-down patient
  without neuro signs.
- Emit only facts that are present. Never emit nulls. Keep it short.
- If nothing matches, return {"f": []}."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["f"],
    "properties": {"f": {"type": "array", "maxItems": 16, "items": {
        "type": "array", "minItems": 3, "maxItems": 3,
        # Values are typed and bounded: an unbounded "any" value let the model ramble until max_tokens
        # (audit 2026-09-23: 5 of 90 calls truncated at 256 tokens, ~4.1 s each).
        "prefixItems": [{"type": "string", "enum": list(KEYS)},
                        {"anyOf": [{"type": "number"}, {"type": "boolean"},
                                   {"type": "string", "maxLength": 48},
                                   {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 40}}]},
                        {"type": "string", "maxLength": 24}],
    }}},
}
ROLE = {"m": Role.medic, "p": Role.patient, "f": Role.family, "b": Role.bystander}

# Worked examples (not from the gold set). They teach the compact format, attribution, and conventions.
EXAMPLES = [
    ("54-year-old male, chest pain, wife says he takes Eliquis, BP 150 over 92, sat 97 on room air.",
     '{"f":[["patient.age",54,"m"],["patient.sex","M","m"],["complaint.chief","chest pain","m"],'
     '["meds.anticoagulant","apixaban","f:wife"],["meds.list",["apixaban"],"f:wife"],["vitals.sbp",150,"m"],'
     '["vitals.dbp",92,"m"],["vitals.spo2",97,"m"],["vitals.on_oxygen",false,"m"]]}'),
    ("Right facial droop, right arm drifts, can't lift the right leg, patient says no allergies, glucose one eighteen.",
     '{"f":[["stroke.deficits",["right facial droop"],"m"],["exam.race.facial",2,"m"],["exam.race.arm",1,"m"],'
     '["exam.race.leg",2,"m"],["allergies",[],"p"],["vitals.glucose",118,"m"]]}'),
    ("Pulse was 88, correction, 98. Son says she was normal at 9 this morning. Unit 12 en route.",
     '{"f":[["vitals.hr",98,"m"],["stroke.lkw","9 am","f:son"]]}'),
]


# The fine-tuned extractor (scripts/train_lora.py) is trained on this short prompt with no key list and no
# examples, and must be called with it. Served model names listed in HERALD_FINETUNED_MODELS use it.
SHORT_SYSTEM = ("Extract EMS facts from the paramedic's words as compact JSON {\"f\": [[key, value, who], ...]}. "
                "who: m medic, p patient, f:<relation> family, b bystander. Only stated facts.")
FINETUNED = {m.strip() for m in os.getenv("HERALD_FINETUNED_MODELS", "ems").split(",") if m.strip()}


def prompt_for(model: Optional[str]) -> tuple[str, Optional[list], Optional[dict]]:
    """(system prompt, worked examples, output schema) for the served model.

    The fine-tuned model decodes in plain JSON mode: under the strict schema (then allowing an optional 4th "?"
    element) it appended "?" to 49 of 49 facts on 10 dev utterances (never seen in training), and a 3-element
    schema cost +35% tokens. Keys and values are still validated against KEYS below. Rows are exactly
    [key, value, who]: the optional "?" element also sent Omni into a degenerate mode (2026-09-23 audit:
    "?" on every fact, invented normal vitals, repeated keys to the token cap) and was redundant, because
    model-only facts already arrive unconfirmed (pipeline.merge_llm)."""
    if model in FINETUNED:
        return SHORT_SYSTEM, None, None
    return SYSTEM.replace("{keys}", _key_list()), EXAMPLES, SCHEMA


def _key_list() -> str:
    return "; ".join(f"{k} [{v['type']}]" for k, v in KEYS.items())


_FILLER = {"", "?", "unknown", "n/a", "na", "not stated", "not mentioned", "none stated", "null"}


def _grounded(key: str, value, text: str) -> bool:
    """Drop filler and ungrounded numbers. The model must not invent a vital sign."""
    if value is None or (isinstance(value, str) and value.strip().lower() in _FILLER):
        return False
    if isinstance(value, list) and any(str(v).strip().lower() in _FILLER for v in value):
        return False
    if key.startswith("vitals.") and isinstance(value, (int, float)) and not isinstance(value, bool):
        if value <= 0:
            return False
        digits = re.findall(r"\d+(?:\.\d+)?", text)
        if digits and key != "vitals.temp":      # spoken-number utterances have no digits; trust the model there
            return any(abs(float(d) - float(value)) < 0.05 for d in digits)
    if key == "vitals.consciousness" and not re.search(
            r"alert|confus|disorient|voice|verbal|pain|unrespons|a ?& ?o|oriented", text, re.I):
        return False
    if key == "code_status" and not re.search(r"dnr|polst|resusc|full code|dni", text, re.I):
        return False
    # Exam findings and witness status must be grounded in words that were actually said. Live test
    # (2026-09-23): from "sudden left-sided weakness" the model invented four RACE item scores.
    need = {
        "exam.race.facial": r"face|facial|droop|smile|palsy|asymmetr",
        "exam.race.arm": r"\barm",
        "exam.race.leg": r"\bleg",
        "exam.race.gaze": r"gaze|eyes?\b|look(ing|s)? (to|toward)|deviat",
        "exam.race.aphasia_agnosia": r"speak|speech|aphasi|agnosi|recogni|neglect|words",
        "stroke.onset_witnessed": r"witness|saw (it|her|him)|in front of|found|woke|collapsed|watched",
        "vitals.gcs_motor": r"gcs|motor|obey|command|localiz|withdraw|flex|extens",
    }.get(key)
    if need and not re.search(need, text, re.I):
        return False
    return True


def extract(text: str, captured_by: CapturedBy = CapturedBy.medic,
            default_role: Role = Role.medic, default_speaker: Optional[str] = None,
            audio_id: Optional[str] = None) -> list[FactIn]:
    usage: dict = {}
    model = llm.model_name()
    system, examples, schema = prompt_for(model)
    data = llm.chat_json(system, text, schema=schema, max_tokens=160, usage=usage, examples=examples)
    out: list[FactIn] = []
    tag = f"llm:{model}"
    for row in data.get("f", []):
        if (not isinstance(row, list) or len(row) < 3 or not isinstance(row[0], str) or row[0] not in KEYS
                or row[1] is None):
            continue
        key, value, who = row[0], row[1], str(row[2] or "m")
        if not _grounded(key, value, text):
            continue
        if key == "patient.sex" and isinstance(value, str):
            value = {"female": "F", "woman": "F", "f": "F", "male": "M", "man": "M", "m": "M"}.get(value.strip().lower(), value)
        code, _, relation = who.partition(":")
        role = ROLE.get(code[:1].lower(), default_role)
        if role == Role.medic and default_role != Role.medic:
            role = default_role          # e.g. the daughter speaking into the mic
        speaker = relation or (default_speaker if role == default_role else None)
        out.append(FactIn(key=key, value=value, role=role, speaker=speaker, captured_by=captured_by,
                          confidence=0.9,
                          provenance=Provenance(audio_id=audio_id, text=text, extractor=tag)))
    extract.last_usage = usage
    return out
