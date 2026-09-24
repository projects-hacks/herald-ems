"""How each served extractor is called (config/extraction.yaml): a fine-tuned model gets the prompt it was trained on
and the same first lines it was trained with (from run D on, who is speaking; from run E on, the call's dispatch).
The same code builds the training inputs (scripts/build_train_set.py), so training and serving can't drift apart."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Optional

from ..config import load_text, load_yaml
from ..core.schema import CapturedBy


@dataclass(frozen=True)
class Profile:
    label_prefix: str
    prompt: str                                  # the system prompt text
    speaker: Optional[dict] = None               # line formats: medic / other / other_unknown
    dispatch: Optional[str] = None               # line format with {dispatch}
    dispatch_unknown: Optional[str] = None
    default: bool = field(default=False, compare=False)

    @property
    def speaker_line(self) -> bool:
        return self.speaker is not None

    def lines(self, captured_by: CapturedBy | str, speaker: Optional[str], dispatch: Optional[str]) -> list[str]:
        out = []
        if self.dispatch:
            d = (dispatch or "").strip()
            out.append(self.dispatch.format(dispatch=d) if d else self.dispatch_unknown)
        if self.speaker:
            if CapturedBy(captured_by) == CapturedBy.medic:
                out.append(self.speaker["medic"])
            else:
                out.append(self.speaker["other"].format(speaker=speaker) if speaker else self.speaker["other_unknown"])
        return out


class Profiles:
    def __init__(self, cfg: dict, extra_finetuned: Iterable[str] = ()):
        self.profiles = [Profile(p["label_prefix"], load_text(p["prompt"]), p.get("speaker"), p.get("dispatch"),
                                 p.get("dispatch_unknown"), bool(p.get("default"))) for p in cfg["finetuned"]]
        self.default = next((p for p in self.profiles if p.default), None)
        self.extra = set(extra_finetuned)

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

    def model_input(self, profile: Optional[Profile], text: str, captured_by: CapturedBy | str,
                    speaker: Optional[str], dispatch: Optional[str] = None) -> str:
        lines = profile.lines(captured_by, speaker, dispatch) if profile is not None else []
        return "\n".join(lines + [text])


@lru_cache(maxsize=1)
def default_profiles() -> Profiles:
    return Profiles.from_config()
