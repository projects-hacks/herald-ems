"""Deterministic extractor: transcript text -> FactIn list.

Fallback when the local LLM is unavailable, and the baseline in the
extraction benchmark. Every fact carries the sentence it came from and a
confidence; ambiguous mappings get low confidence so the medic confirms them.
"""
from __future__ import annotations

import re
from typing import Optional

from .schema import CapturedBy, FactIn, Provenance, Role

ROLE_WORDS = {
    "husband": "family", "wife": "family", "daughter": "family", "son": "family",
    "mother": "family", "father": "family", "mom": "family", "dad": "family",
    "family": "family", "brother": "family", "sister": "family", "caregiver": "family",
    "patient": "patient", "bystander": "bystander", "neighbor": "bystander",
    "neighbour": "bystander", "witness": "bystander",
}
ATTR_RE = re.compile(
    r"\b(?:per (?:the |her |his )?(" + "|".join(ROLE_WORDS) + r")\b"
    r"|(?:the |her |his )?(" + "|".join(ROLE_WORDS) + r")\s+(?:\w+\s+){0,2}?"
    r"(?:says|said|states|stated|reports|reported|denies|denied|tells|told|confirms|thinks))",
    re.I)

ANTICOAG = {
    "warfarin": "warfarin", "coumadin": "warfarin", "jantoven": "warfarin",
    "apixaban": "apixaban", "eliquis": "apixaban", "rivaroxaban": "rivaroxaban",
    "xarelto": "rivaroxaban", "dabigatran": "dabigatran", "pradaxa": "dabigatran",
    "edoxaban": "edoxaban", "savaysa": "edoxaban", "enoxaparin": "enoxaparin",
    "lovenox": "enoxaparin", "heparin": "heparin",
}

_S = r"[^0-9.]{0,14}"   # short gap without digits or sentence end
NUM_PATTERNS = [
    ("vitals.hr", re.compile(r"\b(?:pulse|heart rate|hr)\b" + _S + r"(\d{2,3})\b", re.I), 0.95),
    ("vitals.rr", re.compile(r"\b(?:respiratory rate|resp(?:iratory)? rate|resps|respirations|breathing|rr)\b" + _S + r"(\d{1,2})\b", re.I), 0.93),
    ("vitals.spo2", re.compile(r"\b(?:spo2|sp o2|o2 sat(?:uration)?|oxygen saturation|sat(?:uration|ting|s)?|pulse ox)\b" + _S + r"(\d{2,3})\b", re.I), 0.95),
    ("vitals.glucose", re.compile(r"\b(?:glucose|blood sugar|sugar|bgl|cbg|d-?stick)\b" + _S + r"(\d{2,3})\b", re.I), 0.95),
    ("vitals.gcs_motor", re.compile(r"\b(?:gcs )?motor(?: score)?\b" + _S + r"([1-6])\b", re.I), 0.85),
]
BP_RE = re.compile(r"\b(?:bp|blood pressure|pressure)\b" + _S + r"(\d{2,3})\s*(?:over|/)\s*(\d{2,3})\b", re.I)
TEMP_RE = re.compile(r"\b(?:temp|temperature)\b" + _S + r"(\d{2,3}(?:\.\d)?)\b", re.I)
AGE_SEX_RE = re.compile(
    r"\b(\d{1,3})\s*(?:-|\s)?\s*(?:(?:year|yr)s?[\s-]*old|yo|y/o|yr)\s*(male|female|man|woman|gentleman|lady|m|f)?\b"
    r"|\b(\d{1,3})\s*(yom|yof)\b", re.I)
LKW_RE = re.compile(
    r"\b(?:last (?:known|seen) (?:well|normal)|(?:was )?(?:fine|normal|okay|ok) (?:at|until|around)|last normal)\b"
    r"[^0-9]{0,12}(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)", re.I)
ETA_RE = re.compile(r"\beta\b(?:\s+(?:is|of))?\s*(\d{1,3})\s*(?:min|minutes)?|\b(\d{1,3})\s*minutes?\s+out\b", re.I)
DEST_RE = re.compile(r"\b(?:transporting|taking (?:her|him|them|the patient)|en route|heading|going)\s+to\s+([A-Za-z][\w .'&-]{2,40}?)(?=[,.;]|\s+(?:eta|with|now|code)\b|$)", re.I)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _attribution(sentence: str) -> tuple[Optional[str], Optional[str]]:
    m = ATTR_RE.search(sentence)
    if not m:
        return None, None
    word = (m.group(1) or m.group(2)).lower()
    return ROLE_WORDS[word], word


def extract(text: str, captured_by: CapturedBy = CapturedBy.medic,
            default_role: Role = Role.medic, default_speaker: Optional[str] = None,
            audio_id: Optional[str] = None) -> list[FactIn]:
    out: list[FactIn] = []
    for sentence in _sentences(text):
        # Attribution is per clause: in "68-year-old female, husband says she was
        # fine at 1:40" only the second clause is the husband's.
        for sent in [c.strip() for c in re.split(r"[,;]\s*", sentence) if c.strip()]:
            out.extend(_extract_clause(sent, captured_by, default_role, default_speaker, audio_id))
    return out


def _extract_clause(sent: str, captured_by: CapturedBy, default_role: Role,
                    default_speaker: Optional[str], audio_id: Optional[str]) -> list[FactIn]:
    out: list[FactIn] = []
    if True:
        role_s, speaker = _attribution(sent)
        role = Role(role_s) if role_s else default_role
        speaker = speaker or default_speaker
        low = sent.lower()

        def add(key, value, conf=0.9, unit=None):
            out.append(FactIn(key=key, value=value, unit=unit, role=role, speaker=speaker,
                              captured_by=captured_by, confidence=conf,
                              provenance=Provenance(audio_id=audio_id, text=sent, extractor="rules")))

        m = AGE_SEX_RE.search(sent)
        if m:
            age = m.group(1) or m.group(3)
            sex = (m.group(2) or m.group(4) or "").lower()
            add("patient.age", int(age), 0.95)
            if sex:
                add("patient.sex", "F" if sex.startswith(("f", "w", "l")) or sex == "yof" else "M", 0.95)
        elif re.search(r"\b(female|male)\b", low):
            add("patient.sex", "F" if "female" in low else "M", 0.9)

        m = BP_RE.search(sent)
        if m:
            add("vitals.sbp", int(m.group(1)), 0.95, "mmHg")
            add("vitals.dbp", int(m.group(2)), 0.95, "mmHg")
        for key, rx, conf in NUM_PATTERNS:
            m = rx.search(sent)
            if m:
                add(key, int(m.group(1)), conf)
        m = TEMP_RE.search(sent)
        if m:
            t = float(m.group(1))
            add("vitals.temp", round((t - 32) * 5 / 9, 1) if t > 45 else t, 0.9, "°C")
        if re.search(r"\broom air\b", low):
            add("vitals.on_oxygen", False, 0.95)
        elif re.search(r"\b(?:on|placed on|given|started)\b[^.]{0,25}\b(?:oxygen|o2|nasal cannula|non-?rebreather|nrb)\b", low):
            add("vitals.on_oxygen", True, 0.9)

        for rx, level in [(r"\bunresponsive\b", "U"), (r"\bresponds? (?:only )?to pain", "P"),
                          (r"\bresponds? (?:only )?to (?:voice|verbal)", "V"),
                          (r"\b(?:new )?(?:confusion|confused|disoriented)\b", "C"),
                          (r"\b(?:alert and oriented|a ?(?:&|and) ?o|alert)\b", "A")]:
            if re.search(rx, low) and not re.search(r"\bnot " + rx[2:], low):
                add("vitals.consciousness", level, 0.85)
                break

        m = LKW_RE.search(sent)
        if m:
            add("stroke.lkw", m.group(1).replace(".", "").strip(), 0.9)
        if re.search(r"\b(?:unwitnessed|not witnessed|found (?:down|on the floor|her|him)|woke up with)\b", low):
            add("stroke.onset_witnessed", False, 0.9)
        elif re.search(r"\bwitnessed\b", low):
            add("stroke.onset_witnessed", True, 0.9)

        deficits = re.findall(r"\b(?:(?:left|right)[- ]sided (?:weakness|numbness|facial droop)|facial droop|slurred speech|aphasia|can'?t speak|arm drift|gaze deviation)\b", low)
        if deficits:
            add("stroke.deficits", list(dict.fromkeys(deficits)), 0.9)
            add("complaint.chief", "suspected stroke", 0.9)
        if re.search(r"\bchest pain\b", low):
            add("complaint.chief", "chest pain", 0.9)

        # RACE items. Unqualified wording gets lower confidence -> medic confirms.
        if re.search(r"\b(?:mild|slight|minor)\b[^.]{0,15}\bfacial (?:droop|palsy|asymmetry)", low):
            add("exam.race.facial", 1, 0.9)
        elif re.search(r"\b(?:severe|complete|moderate)\b[^.]{0,15}\bfacial (?:droop|palsy)", low):
            add("exam.race.facial", 2, 0.9)
        elif re.search(r"\bfacial (?:droop|palsy)\b|\bface (?:is )?drooping\b", low):
            add("exam.race.facial", 2, 0.7)
        elif re.search(r"\b(?:no facial droop|face (?:is )?symmetric)", low):
            add("exam.race.facial", 0, 0.9)
        for limb in ("arm", "leg"):
            if re.search(r"(?:can'?t|cannot|unable to) (?:lift|raise|move)\b[^.]{0,30}\b" + limb, low) or \
               re.search(r"\b" + limb + r"\b[^.]{0,20}(?:can'?t|cannot|unable to) (?:lift|raise|move)", low):
                add(f"exam.race.{limb}", 2, 0.9)
            elif re.search(r"\b" + limb + r" drift", low):
                add(f"exam.race.{limb}", 1, 0.85)
            elif re.search(r"\b" + limb + r"s? (?:normal|strong|equal)", low):
                add(f"exam.race.{limb}", 0, 0.85)
        if re.search(r"\b(?:no gaze deviation|gaze (?:is )?normal)", low):
            add("exam.race.gaze", 0, 0.9)
        elif re.search(r"\b(?:gaze deviation|eyes? (?:are )?deviated|gaze (?:to|towards) the|head and eyes? (?:turned|deviated))", low):
            add("exam.race.gaze", 1, 0.9)
        if re.search(r"\b(?:doesn'?t|does not) recogni[sz]e (?:her|his) (?:arm|weakness)[^.]{0,20}\b(?:or|nor|and) (?:the |her |his )?(?:weakness|arm|deficit)", low):
            add("exam.race.aphasia_agnosia", 2, 0.85)
        elif re.search(r"\b(?:doesn'?t|does not) recogni[sz]e (?:her|his) (?:arm|weakness|deficit)", low):
            add("exam.race.aphasia_agnosia", 1, 0.85)
        elif re.search(r"\b(?:aphasic|global aphasia|can'?t speak|unable to speak|no speech)\b", low):
            add("exam.race.aphasia_agnosia", 2, 0.85)
        elif re.search(r"\b(?:speech (?:is )?normal|speaking normally|no aphasia|no agnosia|no neglect|recogni[sz]es (?:her|his) arm)\b", low):
            add("exam.race.aphasia_agnosia", 0, 0.85)

        if re.search(r"\b(?:no|not on (?:any )?|denies|without)\s*(?:blood thinners|anticoagulants?)\b", low):
            add("meds.anticoagulant", "none", 0.9)
        for name, canon in ANTICOAG.items():
            if re.search(r"\b" + name + r"\b", low):
                add("meds.anticoagulant", canon, 0.9)
                add("meds.list", [canon], 0.9)
                break

        if re.search(r"\b(?:no known (?:drug )?allergies|nkda|no allergies|denies (?:any )?allergies)\b", low):
            add("allergies", [], 0.9)
        else:
            m = re.search(r"\ballerg(?:ic|y) to ([a-z][a-z -]{2,30}?)(?=[.,;!?]|\s+and\b|$)", low)
            if m:
                add("allergies", [m.group(1).strip()], 0.9)

        if re.search(r"\b(?:dnr|do not resuscitate|polst|dni)\b", low):
            add("code_status", "DNR/POLST mentioned: verify form", 0.7)
        elif re.search(r"\bfull code\b", low):
            add("code_status", "full code", 0.8)

        m = ETA_RE.search(sent)
        if m:
            add("transport.eta_min", int(m.group(1) or m.group(2)), 0.9)
        m = DEST_RE.search(sent)
        if m:
            add("transport.destination", m.group(1).strip().title(), 0.85)
    return out
