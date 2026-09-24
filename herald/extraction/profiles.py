"""How each served extractor is called (config/extraction.yaml): a fine-tuned model gets the prompt it was trained
on and, from run D on, a first line saying whose mic the words came from. The same code builds the training inputs
(scripts/build_train_set.py), so training and serving can't drift apart."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Optional

from ..config import load_text, load_yaml
from ..core.schema import CapturedBy


@dataclass(frozen=True)
class Profile:
    label_prefix: str
    prompt: str                  # the system prompt text
    speaker_line: bool


class Profiles:
    def __init__(self, cfg: dict, extra_finetuned: Iterable[str] = ()):
        self.profiles = [Profile(p["label_prefix"], load_text(p["prompt"]), bool(p.get("speaker_line")))
                         for p in cfg["finetuned"]]
        self.default = next((Profile(p["label_prefix"], load_text(p["prompt"]), bool(p.get("speaker_line")))
                             for p in cfg["finetuned"] if p.get("default")), None)
        self.extra = set(extra_finetuned)
        self.lines = cfg["speaker_line"]

    @classmethod
    def from_config(cls, extra_finetuned: Iterable[str] = ()) -> "Profiles":
        return cls(load_yaml("extraction.yaml"), extra_finetuned)

    def for_label(self, label: Optional[str]) -> Optional[Profile]:
        """The fine-tuned profile for a served label, or None for a general model."""
        if not label:
            return None
        for p in self.profiles:
            if label == p.label_prefix or label.startswith(p.label_prefix + "-"):
                return p
        return self.default if label in self.extra else None

    def speaker_line(self, captured_by: CapturedBy | str, speaker: Optional[str]) -> str:
        if CapturedBy(captured_by) == CapturedBy.medic:
            return self.lines["medic"]
        return self.lines["other"].format(speaker=speaker) if speaker else self.lines["other_unknown"]

    def model_input(self, profile: Optional[Profile], text: str, captured_by: CapturedBy | str,
                    speaker: Optional[str]) -> str:
        if profile is not None and profile.speaker_line:
            return f"{self.speaker_line(captured_by, speaker)}\n{text}"
        return text


@lru_cache(maxsize=1)
def default_profiles() -> Profiles:
    return Profiles.from_config()
