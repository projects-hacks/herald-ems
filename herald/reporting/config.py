"""The handoff formats as reviewed content (config/handoff.yaml), loaded and checked once at startup."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

from ..config import load_yaml

REQUIRED_WORDS = ("missing", "empty_list", "arrow", "list_separator", "line_separator", "missing_heading",
                  "unconfirmed_heading", "differs", "unit_no_space", "not_obtained", "not_obtained_heading")


def _flatten(lines: Iterable) -> list[dict]:
    """`lines` may splice in shared lists (YAML anchors): nested lists are flattened, in order."""
    out: list[dict] = []
    for x in lines:
        out.extend(_flatten(x) if isinstance(x, list) else [x])
    return out


@dataclass(frozen=True)
class HandoffConfig:
    formats: dict[str, dict]
    select: list[dict]
    default: str
    words: dict[str, Any]
    value_text: dict[str, dict[str, str]]
    score_text: dict[str, dict[str, str]]
    time_format: str
    # score id -> criterion id -> spoken templates (the first whose placeholders all have confirmed values)
    criteria_say: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # who told us what: {"heading", "rest", "labels": {role: how the report names it}}
    informants: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffConfig":
        formats = {}
        for fid, f in d["formats"].items():
            sections = [{**s, "lines": _flatten(s.get("lines", []))} for s in f["sections"]]
            formats[fid] = {**f, "id": fid, "sections": sections}
        value_text = {k: {str(w).strip().lower(): str(t) for w, t in m.items()} for k, m in d["value_text"].items()}
        say = {sid: {str(cid): [t] if isinstance(t, str) else list(t) for cid, t in (m or {}).items()}
               for sid, m in (d.get("criteria_say") or {}).items()}
        return cls(formats, list(d.get("select", [])), d["default"], dict(d["words"]), value_text,
                   d["score_text"], d["time_format"], say, dict(d.get("informants") or {}))

    @classmethod
    def from_config(cls, rel: str = "handoff.yaml") -> "HandoffConfig":
        return cls.from_dict(load_yaml(rel))

    def lines(self) -> Iterable[tuple[str, str, dict]]:
        for fid, f in self.formats.items():
            for s in f["sections"]:
                for spec in s["lines"]:
                    yield fid, s["id"], spec

    def problems(self, vocabulary, scales, kinds: dict, checklist_ids: Iterable[str], trends=None) -> list[str]:
        """Everything wrong with the content against the loaded vocabulary, scores, line kinds, checklists and (when
        given) the trend change rules."""
        errs = [f"words: missing {w}" for w in REQUIRED_WORDS if w not in self.words]
        errs += [f"informants: missing {w}" for w in ("heading", "rest", "labels") if w not in self.informants]
        checklists = set(checklist_ids)
        known_formats = set(self.formats)
        if self.default not in known_formats:
            errs.append(f"default format {self.default!r} is not defined")
        for rule in self.select:
            if rule["format"] not in known_formats:
                errs.append(f"select: unknown format {rule['format']!r}")
            errs += [f"select: unknown checklist {c!r}" for c in rule.get("checklists", []) if c not in checklists]
        for fid, f in self.formats.items():
            for field in ("label", "title", "source"):
                if not f.get(field):
                    errs.append(f"{fid}: needs {field}")
            ids = [s["id"] for s in f["sections"]]
            if len(ids) != len(set(ids)):
                errs.append(f"{fid}: duplicate section ids")
        for fid, sid, spec in self.lines():
            where = f"{fid}.{sid}"
            kind = kinds.get(spec.get("kind"))
            if kind is None:
                errs.append(f"{where}: unknown line kind {spec.get('kind')!r}")
                continue
            errs += [f"{where}: {e}" for e in kind.problems(spec, vocabulary, scales, self, trends=trends)]
            gates = list(spec.get("when_checklists", []))
            if isinstance(spec.get("required"), list):
                gates += spec["required"]
            errs += [f"{where}: unknown checklist {c!r}" for c in gates if c not in checklists]
        errs += [f"criteria_say: unknown score {sid!r}" for sid in self.criteria_say if sid not in scales]
        for key in self.value_text:
            base = key if key in vocabulary else key.rsplit(".", 1)[0]
            if base not in vocabulary:
                errs.append(f"value_text: unknown key {key!r}")
        return errs


@lru_cache(maxsize=1)
def default_handoff_config() -> HandoffConfig:
    return HandoffConfig.from_config()
