"""Photo -> facts with the local vision-language model. Every fact from a photo starts
unconfirmed; the medic taps to confirm. Reading only: no interpretation of ECGs, no advice."""
from __future__ import annotations

import base64
from typing import Optional

from . import llm
from .extract_rules import ANTICOAG
from .schema import CapturedBy, FactIn, Provenance, Role

PROMPTS = {
    "monitor": ("This is a photo of a pulse oximeter or patient monitor screen. Read ONLY numbers that are clearly "
                "visible. Return JSON {\"facts\":[{\"key\":k,\"value\":number,\"confidence\":0-1,\"box\":[x0,y0,x1,y1]}]} "
                "using keys vitals.spo2 (SpO2 %), vitals.hr (pulse/heart rate), vitals.sbp, vitals.dbp, vitals.rr. "
                "Boxes are normalized 0-1. If a value is not clearly readable, omit it."),
    "pill_bottle": ("This is a photo of a prescription medication label. Return JSON {\"facts\":[{\"key\":\"meds.list\","
                    "\"value\":[\"<generic or brand drug name, lowercase>\"],\"strength\":\"<e.g. 5 mg>\",\"confidence\":0-1,"
                    "\"box\":[x0,y0,x1,y1]}]}. Read only what is printed. If unreadable, return {\"facts\":[]}."),
    "form": ("This is a photo of a medical order form such as a California POLST. Report which resuscitation box is "
             "checked, exactly as printed. Return JSON {\"facts\":[{\"key\":\"code_status\",\"value\":\"<checked option text>\","
             "\"confidence\":0-1,\"box\":[x0,y0,x1,y1]}]}. If no box is clearly checked, return {\"facts\":[]}."),
    "scene": ("This is a photo of the room a patient was found in. List up to 4 short, factual, non-judgmental "
              "observations useful to an emergency department (mobility aids, oxygen equipment, medication organizers "
              "and whether doses remain, fall hazards). Return JSON {\"facts\":[{\"key\":\"scene.notes\",\"value\":[\"...\"],"
              "\"confidence\":0-1}]}. No guesses about the person."),
}


# Physiological plausibility: a photo reading outside these ranges is dropped, never shown as a fact.
RANGES = {"vitals.spo2": (50, 100), "vitals.hr": (20, 250), "vitals.sbp": (50, 260), "vitals.dbp": (20, 180),
          "vitals.rr": (4, 60)}


def read_photo(image_bytes: bytes, mode: str, photo_id: Optional[str] = None) -> list[FactIn]:
    if mode not in PROMPTS:
        raise ValueError(f"mode must be one of {list(PROMPTS)}")
    data = llm.chat_json("You read photos for a paramedic's record. Output strict JSON only.",
                         PROMPTS[mode], image_b64=base64.b64encode(image_bytes).decode(), max_tokens=400)
    out: list[FactIn] = []
    tag = f"vision:{llm.model_name()}"
    for f in data.get("facts", []):
        key, value = f.get("key"), f.get("value")
        if key is None or value in (None, "", []):
            continue
        if key in RANGES:
            try:
                lo, hi = RANGES[key]
                if not (lo <= float(value) <= hi):
                    continue
            except (TypeError, ValueError):
                continue
        prov = Provenance(photo_id=photo_id, crop=f.get("box"), extractor=tag,
                          text=f.get("strength") and f"{value} {f['strength']}")
        common = dict(role=Role.photo, speaker=mode.replace("_", " "), captured_by=CapturedBy.camera,
                      confidence=float(f.get("confidence", 0.8)), provenance=prov)
        out.append(FactIn(key=key, value=value, **common))
        if key == "meds.list":
            names = value if isinstance(value, list) else [value]
            for n in names:
                canon = ANTICOAG.get(str(n).lower().split()[0])
                if canon:
                    out.append(FactIn(key="meds.anticoagulant", value=canon, **common))
    sbp = next((f.value for f in out if f.key == "vitals.sbp"), None)
    dbp = next((f.value for f in out if f.key == "vitals.dbp"), None)
    if sbp is not None and dbp is not None and float(dbp) >= float(sbp):
        out = [f for f in out if f.key not in ("vitals.sbp", "vitals.dbp")]
    return out
