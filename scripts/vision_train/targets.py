"""Prompts and target answers, both taken from the production config at build time.

The prompt text is config/prompts/vision.yaml (the same file VisionReader loads), never a copy. The target is the
JSON that prompt asks for, projected from the example's truth:
- only keys the mode prompt names (so a reading the prompt doesn't ask for, e.g. EtCO2 today, is left out, and is
  included automatically once the prompt names it: rebuild with `make.py --retarget`);
- values in the vocabulary's type (int, one-decimal float, list of one generic name), inside the photo
  plausibility ranges the reader applies;
- fields in the prompt's order: key, value, strength (label mode), confidence, box (normalized 0-1);
- unreadable readings omitted; facts in reading order (top to bottom, left to right)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

from herald.config import load_text, load_yaml
from herald.core.vocabulary import default_vocabulary

from .spec import Reading

VOCAB = default_vocabulary()
SEPARATORS = (",", ":")                       # compact, as the prompt writes its JSON


@dataclass
class Prompts:
    system: str
    modes: dict[str, str]
    ranges: dict[str, tuple[float, float]]
    sha: str

    @classmethod
    def load(cls) -> "Prompts":
        cfg = load_yaml("prompts/vision.yaml")
        sha = hashlib.sha256(load_text("prompts/vision.yaml").encode()).hexdigest()[:12]
        return cls(cfg["system"], dict(cfg["modes"]), {k: tuple(v) for k, v in cfg["plausible_ranges"].items()}, sha)

    def scope(self, mode: str) -> set[str]:
        """Vocabulary keys the mode prompt names."""
        prompt = self.modes[mode]
        return {k for k in VOCAB.keys if re.search(rf"(?<![\w.]){re.escape(k)}(?![\w.])", prompt)}

    def asks(self, mode: str, field: str) -> bool:
        return f'"{field}"' in self.modes[mode]


def _plausible(ranges, key: str, value) -> bool:
    if key not in ranges:
        return True
    lo, hi = ranges[key]
    return lo <= float(value) <= hi


def confidence(severity: float, box: Optional[tuple]) -> float:
    """0.97 on a clean, large reading, lower with photo effects and small print (the medic confirms every photo
    fact anyway; this only has to rank)."""
    c = 0.97 - 0.3 * severity
    if box and (box[3] - box[1]) < 0.035:
        c -= 0.05
    return round(max(0.6, min(0.97, c)), 2)


def build(mode: str, readings: list[Reading], severity: float, prompts: Prompts) -> dict:
    """The exact answer object for one photo."""
    scope = prompts.scope(mode)
    facts = []
    order = sorted((r for r in readings if r.box), key=lambda r: (round(r.box[1] * 20), r.box[0]))
    order += [r for r in readings if not r.box]
    seen = set()
    for r in order:
        if not r.readable or r.key not in scope:
            continue
        meta = VOCAB.meta(r.key)
        value = VOCAB.validate(r.key, [r.value] if meta.get("type") == "list" else r.value)
        if meta.get("type") == "float":
            value = round(float(value), 1)
        if meta.get("type") != "list" and not _plausible(prompts.ranges, r.key, value):
            continue
        ident = (r.key, json.dumps(value))
        if ident in seen:
            continue
        seen.add(ident)
        f = {"key": r.key, "value": value}
        if r.strength and r.strength_readable and prompts.asks(mode, "strength"):
            f["strength"] = r.strength
        if prompts.asks(mode, "confidence"):
            f["confidence"] = confidence(severity, r.box)
        if r.box and prompts.asks(mode, "box"):
            f["box"] = [round(max(0.0, min(1.0, v)), 3) for v in r.box]
        facts.append(f)
    return {"facts": facts}


def dumps(target: dict) -> str:
    return json.dumps(target, separators=SEPARATORS, ensure_ascii=False)


def messages(system: str, user: str, image_path: str, answer: str) -> list[dict]:
    """The chat the production client sends (herald/models/llm_client.py chat_json: system, then the user text
    followed by the image), plus the answer."""
    return [{"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": user}, {"type": "image", "image": image_path}]},
            {"role": "assistant", "content": answer}]
