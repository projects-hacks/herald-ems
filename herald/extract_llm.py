"""LLM extractor: transcript -> typed facts with source role. Local model only.

The model maps speech to our schema. It never computes scores, never decides
what is sent, and never gives advice. Output is validated against KEYS; anything
invalid is dropped, and the rules extractor still runs as the safety net.
"""
from __future__ import annotations

from typing import Optional

from . import llm
from .schema import KEYS, CapturedBy, FactIn, Provenance, Role

SYSTEM = """You convert a paramedic's spoken words into structured facts for an EMS record.
Return ONLY JSON: {"f": [[key, value, who], ...]} with one short array per fact and nothing else.
who = "m" medic observed/measured, "p" patient said, "f:<relation>" family said (e.g. "f:husband"), "b" bystander said.
Add a 4th element "?" only when you had to guess a severity or mapping.
Rules:
- Use only these keys (type in brackets): {keys}
- Only facts explicitly stated. Never infer, never diagnose, never add treatment.
- role = who the information came from: medic (observed/measured), patient, family, bystander. "husband says X" -> role family, speaker "husband".
- Blood pressure "148 over 92" -> vitals.sbp 148 and vitals.dbp 92. Temperatures in Fahrenheit -> convert to Celsius.
- vitals.consciousness is one letter: A (alert), C (new confusion), V (responds to voice), P (responds to pain), U (unresponsive).
- RACE items: exam.race.facial 0 none/1 mild/2 moderate-severe; exam.race.arm and exam.race.leg 0 normal/1 drift or holds <10 s/2 cannot lift against gravity; exam.race.gaze 0/1; exam.race.aphasia_agnosia 0 none/1 one of arm or deficit not recognized/2 neither recognized or severe aphasia. If severity is not stated, give your best mapping with confidence <= 0.7.
- "no known allergies" -> allergies []. Anticoagulant named (warfarin, Eliquis/apixaban, Xarelto/rivaroxaban, Pradaxa/dabigatran, Lovenox/enoxaparin) -> meds.anticoagulant (generic name, lowercase); "no blood thinners" -> meds.anticoagulant "none".
- Times like "fine at 1:40" -> stroke.lkw "1:40" as spoken.
- Emit only facts that are present. Never emit nulls. Keep it short.
- If nothing matches, return {"f": []}."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["f"],
    "properties": {"f": {"type": "array", "maxItems": 24, "items": {
        "type": "array", "minItems": 3, "maxItems": 4,
        "prefixItems": [{"type": "string", "enum": list(KEYS)}, {}, {"type": "string", "maxLength": 20},
                        {"type": "string", "enum": ["?"]}],
    }}},
}
ROLE = {"m": Role.medic, "p": Role.patient, "f": Role.family, "b": Role.bystander}


def _key_list() -> str:
    return "; ".join(f"{k} [{v['type']}]" for k, v in KEYS.items())


def extract(text: str, captured_by: CapturedBy = CapturedBy.medic,
            default_role: Role = Role.medic, default_speaker: Optional[str] = None,
            audio_id: Optional[str] = None) -> list[FactIn]:
    usage: dict = {}
    data = llm.chat_json(SYSTEM.replace("{keys}", _key_list()), text, schema=SCHEMA, max_tokens=256, usage=usage)
    out: list[FactIn] = []
    tag = f"llm:{llm.model_name()}"
    for row in data.get("f", []):
        if not isinstance(row, list) or len(row) < 3 or row[0] not in KEYS or row[1] is None:
            continue
        key, value, who = row[0], row[1], str(row[2] or "m")
        code, _, relation = who.partition(":")
        role = ROLE.get(code[:1].lower(), default_role)
        if role == Role.medic and default_role != Role.medic:
            role = default_role          # e.g. the daughter speaking into the mic
        speaker = relation or (default_speaker if role == default_role else None)
        guessed = len(row) > 3 and row[3] == "?"
        out.append(FactIn(key=key, value=value, role=role, speaker=speaker, captured_by=captured_by,
                          confidence=0.7 if guessed else 0.9,
                          provenance=Provenance(audio_id=audio_id, text=text, extractor=tag)))
    extract.last_usage = usage
    return out
