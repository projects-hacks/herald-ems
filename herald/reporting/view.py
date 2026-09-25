"""The incident as the handoff report may see it: confirmed facts only, their provenance, and their wording.

Every value a report line shows comes through `ConfirmedView`. A fact waiting for the medic's tap is never
rendered here; `unconfirmed()` names such facts (key, label, fact ids) without their values, so they can be listed
separately and never leave the vehicle (AGENTS.md invariant 4).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from ..core.clock import parse_clock
from ..core.schema import Fact, Status
from ..core.vocabulary import Vocabulary, norm_value
from .config import HandoffConfig

# {key}, {key:unit}, {key:label}, {key:time}; {$name} is a context value (the vehicle's unit ID)
PLACEHOLDER = re.compile(r"\{(\$?[\w.]+)(?::(\w+))?\}")


def number_text(v: Any) -> str:
    """324.0 -> "324", 0.15 -> "0.15" (a dose keeps its precision)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


class ConfirmedView:
    def __init__(self, incident, vocabulary: Vocabulary, config: HandoffConfig, tz: ZoneInfo,
                 context: Optional[dict] = None):
        self.inc, self.vocab, self.cfg, self.tz = incident, vocabulary, config, tz
        self.values = incident.values(confirmed_only=True)
        self.context = {k: v for k, v in (context or {}).items() if v not in (None, "")}

    # ---------- facts ----------
    def facts_for(self, key: str) -> list[Fact]:
        """The confirmed facts behind a key's value: every one for list and event keys, the latest otherwise."""
        h = self.inc.history(key, confirmed_only=True)
        if self.vocab.meta(key).get("merge") in ("accumulate", "each"):
            return h
        return h[-1:]

    def history(self, key: str) -> list[Fact]:
        return self.inc.history(key, confirmed_only=True)

    def present(self, key: str) -> bool:
        return self.values.get(key) is not None

    def pending(self, key: str) -> bool:
        """A fact for this key waits for the medic's tap."""
        return any(f.key == key and f.status == Status.unconfirmed for f in self.inc.facts)

    def unconfirmed(self) -> list[dict]:
        """Keys with facts waiting for a tap, in the order first heard: names and fact ids, never values."""
        out: dict[str, dict] = {}
        for f in self.inc.facts:
            if f.status != Status.unconfirmed:
                continue
            row = out.setdefault(f.key, {"key": f.key, "label": self.vocab.label(f.key), "fact_ids": [],
                                         "differs": False})
            row["fact_ids"].append(f.id)
            merge = self.vocab.meta(f.key).get("merge")
            if merge is None and self.present(f.key) and norm_value(f.value) != norm_value(self.values[f.key]):
                row["differs"] = True
        return list(out.values())

    def source(self, f: Fact) -> dict:
        """Provenance of one fact, for a line: which fact, who said it, when, and the clip or photo."""
        return {"fact_id": f.id, "key": f.key, "role": f.role.value, "speaker": f.speaker,
                "captured_by": f.captured_by.value, "time": self.clock(f.ts), "ts": f.ts.isoformat(),
                "audio_id": f.provenance.audio_id, "photo_id": f.provenance.photo_id,
                "extractor": f.provenance.extractor,
                "observed_at": f.provenance.observed_at.isoformat() if f.provenance.observed_at else None,
                "frame_id": f.provenance.frame_id}

    # ---------- wording ----------
    def clock(self, ts: datetime) -> str:
        return ts.astimezone(self.tz).strftime(self.cfg.time_format)

    def spoken_time(self, said: Any, at: Optional[datetime]) -> str:
        """A spoken clock time ("1422") as local HH:MM, resolved against when it was said; as said otherwise."""
        t = parse_clock(str(said), self.tz, at) if at is not None else None
        return t.strftime(self.cfg.time_format) if t else str(said)

    def mapped(self, name: str, v: Any) -> Optional[str]:
        words = self.cfg.value_text.get(name) or {}
        return words.get(str(v).strip().lower())

    def value_text(self, key: str, v: Any, at: Optional[datetime] = None) -> str:
        meta = self.vocab.meta(key)
        if (m := self.mapped(key, v)) is not None:
            return m
        if isinstance(v, list):
            return self.cfg.words["list_separator"].join(str(x) for x in v) if v else self.cfg.words["empty_list"]
        if meta["type"] == "time":
            return self.spoken_time(v, at)
        return number_text(v)

    def with_unit(self, text: str, unit: Optional[str]) -> str:
        if not unit:
            return text
        tight = any(unit.startswith(p) for p in self.cfg.words["unit_no_space"])
        return f"{text}{unit}" if tight else f"{text} {unit}"

    def placeholder(self, name: str, mod: Optional[str]) -> Optional[str]:
        """One placeholder's text, or None when its value isn't confirmed (the template then doesn't apply)."""
        if name.startswith("$"):
            v = self.context.get(name[1:])
            return None if v is None else str(v)
        if mod == "label":
            return self.vocab.label(name)
        if not self.present(name):
            return None
        latest = self.facts_for(name)[-1]
        if mod == "time":
            return self.clock(latest.ts)
        text = self.value_text(name, self.values[name], latest.ts)
        if mod == "unit":
            return self.with_unit(text, latest.unit or self.vocab.meta(name).get("unit"))
        return text

    def render(self, template: str) -> Optional[str]:
        """The template with every placeholder filled, or None if any value is not confirmed."""
        parts = {}
        for m in PLACEHOLDER.finditer(template):
            text = self.placeholder(m[1], m[2])
            if text is None:
                return None
            parts[m[0]] = text
        return PLACEHOLDER.sub(lambda m: parts[m[0]], template)

    def record_text(self, key: str, record: dict, parts: list[str], at: Optional[datetime]) -> str:
        """A record (a dose given, a procedure) from its parts; a part is kept only if every field it names is
        recorded."""
        out = []
        for part in parts:
            fields = [m[1] for m in PLACEHOLDER.finditer(part)]
            if any(record.get(f) in (None, "") for f in fields):
                continue
            out.append(PLACEHOLDER.sub(lambda m: self.field_text(key, m[1], record[m[1]], at), part))
        return "".join(out).strip()

    def field_text(self, key: str, field: str, v: Any, at: Optional[datetime]) -> str:
        if (m := self.mapped(f"{key}.{field}", v)) is not None:
            return m
        if self.vocab.meta(key)["fields"].get(field) == "time":
            return self.spoken_time(v, at)
        return number_text(v)


def template_keys(template: str) -> list[str]:
    """The vocabulary keys a template reads (context values and labels excluded)."""
    return [m[1] for m in PLACEHOLDER.finditer(template) if not m[1].startswith("$") and m[2] != "label"]
