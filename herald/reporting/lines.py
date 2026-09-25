"""Line kinds of a handoff report. Each kind turns one line definition (config/handoff.yaml) into zero or more lines,
from confirmed facts and the snapshot's scores only. A new kind is a new class registered in LINE_KINDS; the report
builder never branches on kinds.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.schema import Fact
from ..core.vocabulary import norm_value
from ..scoring.rules import RULES, evaluate, rule_keys
from .config import HandoffConfig
from .view import ConfirmedView, template_keys


@dataclass(frozen=True)
class Line:
    kind: str                            # fact | event | score | trend | missing | empty
    text: str
    status: str = "confirmed"            # confirmed | missing (no confirmed value) | empty (a section with nothing)
    keys: tuple[str, ...] = ()           # the vocabulary keys (and "@<score>") this line covers
    facts: tuple[Fact, ...] = ()         # the confirmed facts it came from
    source: Optional[str] = None         # a score's citation


@dataclass
class BuildContext:
    view: ConfirmedView
    snapshot: dict
    scales: Any
    config: HandoffConfig
    open_checklists: set[str] = field(default_factory=set)

    def required(self, spec: dict) -> bool:
        req = spec.get("required", False)
        return bool(self.open_checklists & set(req)) if isinstance(req, list) else bool(req)

    def absent(self, spec: dict, keys: list[str], label: Optional[str] = None) -> list[Line]:
        """No confirmed value: nothing while a value waits for a tap (listed separately), "not yet known" when the
        line is required, nothing otherwise."""
        if any(self.view.pending(k) for k in keys) or not self.required(spec):
            return []
        name = spec.get("label") or label or (self.view.vocab.label(keys[0]) if keys else "")
        return [Line("missing", f"{name}: {self.config.words['missing']}", status="missing", keys=tuple(keys))]

    def facts(self, keys) -> tuple[Fact, ...]:
        """The confirmed facts behind these keys, in the order they were recorded."""
        order = {f.id: i for i, f in enumerate(self.view.inc.facts)}
        found = {f.id: f for k in keys if self.view.present(k) for f in self.view.facts_for(k)}
        return tuple(sorted(found.values(), key=lambda f: order[f.id]))


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("()", "")).strip()


SCORE_FIELDS = {"name", "score", "band", "level", "max", "cite", "missing"}
HIT_FIELDS = SCORE_FIELDS | {"group", "text"}


def _bad_fields(template: str, allowed: set[str]) -> list[str]:
    used = {f for _, f, _, _ in string.Formatter().parse(template) if f is not None}
    return [f"template {template!r} uses unknown field {f!r}" for f in sorted(used - allowed)]


def _unknown_keys(keys, vocabulary) -> list[str]:
    return [f"unknown key {k!r}" for k in keys if k not in vocabulary]


class FactLine:
    """The first template whose placeholders all have confirmed values."""

    @staticmethod
    def keys(spec: dict) -> list[str]:
        return list(dict.fromkeys([k for t in spec["templates"] for k in template_keys(t)] + spec.get("keys", [])))

    def problems(self, spec, vocabulary, scales, cfg) -> list[str]:
        if not spec.get("templates"):
            return ["a fact line needs templates"]
        errs = _unknown_keys(self.keys(spec), vocabulary)
        if "when" in spec:
            if spec["when"].get("type") not in RULES:
                errs.append(f"unknown rule type {spec['when'].get('type')!r}")
            errs += _unknown_keys(rule_keys(spec["when"]), vocabulary)
        return errs

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        keys = self.keys(spec)
        if "when" in spec and evaluate(spec["when"], ctx.view.values).met is not True:
            return []
        for t in spec["templates"]:
            text = ctx.view.render(t)
            if text is not None:          # covers only what it shows: a fallback template leaves the rest a gap
                shown = list(dict.fromkeys(template_keys(t) + spec.get("keys", [])))
                return [Line("fact", text, keys=tuple(shown), facts=ctx.facts(shown))]
        return ctx.absent(spec, keys)


class EventsLine:
    """Every confirmed event of a record key, in the order recorded; the same event said twice is one line.
    `where` keeps only records whose fields have these values; `where_not` drops them (e.g. `before_arrival: true`
    splits what was given before the crew arrived from the crew's own treatment). A field that wasn't recorded
    matches no value."""

    def problems(self, spec, vocabulary, scales, cfg) -> list[str]:
        key = spec.get("key")
        if key not in vocabulary or vocabulary.meta(key).get("merge") != "each":
            return [f"events needs an event key, got {key!r}"]
        fields = vocabulary.meta(key)["fields"]
        named = [f for p in spec["parts"] for f in template_keys(p)]
        named += [f for opt in ("where", "where_not") for f in (spec.get(opt) or {})]
        return [f"{key} has no field {f!r}" for f in named if f not in fields]

    @staticmethod
    def _matches(record: dict, wanted: dict) -> bool:
        return all(str(record.get(f)).strip().lower() == str(v).strip().lower() for f, v in wanted.items())

    def keep(self, spec: dict, record: dict) -> bool:
        if spec.get("where") and not self._matches(record, spec["where"]):
            return False
        return not (spec.get("where_not") and self._matches(record, spec["where_not"]))

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        key = spec["key"]
        groups: dict[Any, list[Fact]] = {}
        for f in ctx.view.history(key):
            if self.keep(spec, f.value):
                groups.setdefault(norm_value(f.value), []).append(f)
        lines = [Line("event", ctx.view.record_text(key, fs[0].value, spec["parts"], fs[0].ts), keys=(key,),
                      facts=tuple(fs)) for fs in groups.values()]
        return lines or ctx.absent(spec, [key])


class ScoreLine:
    """A score from the snapshot, with its citation. An incomplete score shows what is missing, never a partial
    total; a criteria score shows each met criterion with the facts that decided it."""

    def problems(self, spec, vocabulary, scales, cfg) -> list[str]:
        ids = spec["score"] if isinstance(spec["score"], list) else [spec["score"]]
        errs = [f"unknown score {s!r}" for s in ids if s not in scales]
        if spec.get("only_if"):
            errs += _bad_fields(spec["template"], SCORE_FIELDS) if "template" in spec else ["only_if needs a template"]
        for s in ids:
            kind = scales[s].d["kind"] if s in scales else None
            if kind is not None and kind not in cfg.score_text:
                errs.append(f"no score_text for kind {kind!r}")
            for name, t in (cfg.score_text.get(kind) or {}).items():
                errs += _bad_fields(t, HIT_FIELDS if name == "hit" else SCORE_FIELDS)
        return errs

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        ids = spec["score"] if isinstance(spec["score"], list) else [spec["score"]]
        sid = next((s for s in ids if s in ctx.snapshot["scores"]), None)
        if sid is None:
            return []
        r, scale = ctx.snapshot["scores"][sid], ctx.scales[sid]
        cite = spec.get("cite", "")
        cite = cite.get(sid, "") if isinstance(cite, dict) else cite
        inputs = sorted(scale.input_keys())
        if r.get("applies") is False:
            return []
        fields = {"name": scale.name, "score": r.get("score"), "band": r.get("band"), "level": r.get("level"),
                  "max": getattr(scale, "max_score", None), "cite": cite,
                  "missing": ", ".join(r.get("missing", []))}
        line = lambda text, facts=None: Line("score", _tidy(text), keys=(f"@{sid}",),       # noqa: E731
                                             facts=ctx.facts(inputs) if facts is None else facts,
                                             source=r.get("source"))
        if spec.get("only_if"):
            return [line(spec["template"].format(**fields))] if r.get(spec["only_if"]) is True else []
        if not any(ctx.view.present(k) for k in inputs):
            return ctx.absent(spec, inputs, label=scale.name)
        words = ctx.config.score_text[scale.d["kind"]]
        if scale.d["kind"] == "criteria":
            return self._criteria(spec, ctx, r, scale, words, fields, line)
        return [line(words["complete" if r["complete"] else "incomplete"].format(**fields))]

    @staticmethod
    def _criteria(spec, ctx, r, scale, words, fields, line) -> list[Line]:
        names = spec.get("group_names", {})
        rows = list(zip(scale.criteria_keys(), r["criteria"]))
        out = []
        for g in scale.groups:
            decided = [keys for (gid, keys), row in rows if gid == g["id"] and row["state"] == "met"]
            group = names.get(g["id"], g.get("short", g["id"]))
            for hit, keys in zip(r[g["id"]], decided):
                out.append(line(words["hit"].format(**fields, group=group, text=hit), ctx.facts(sorted(keys))))
        if out:
            return out
        return [line(words["not_met" if r["complete"] else "undecided"].format(**fields))]


class TrendsLine:
    """Every listed key with two or more confirmed readings: the readings in order."""

    def problems(self, spec, vocabulary, scales, cfg) -> list[str]:
        return (_unknown_keys(spec.get("keys", []), vocabulary) + ([] if spec.get("template") else ["needs template"])
                + _bad_fields(spec.get("point_template", "{value}"), {"value", "time"}))

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        v, out = ctx.view, []
        for key in spec["keys"]:
            h = v.history(key)
            if len(h) < 2:
                continue
            point = spec.get("point_template")
            if point:
                series = ctx.config.words["arrow"].join(point.format(
                    value=v.with_unit(v.value_text(key, f.value, f.ts), f.unit or v.vocab.meta(key).get("unit")),
                    time=(f.provenance.observed_at or f.ts).astimezone(v.tz).strftime("%H:%M:%S")) for f in h)
            else:
                series = ctx.config.words["arrow"].join(v.value_text(key, f.value, f.ts) for f in h)
                series = v.with_unit(series, h[-1].unit or v.vocab.meta(key).get("unit"))
            out.append(Line("trend", spec["template"].format(label=v.vocab.label(key), series=series), keys=(key,),
                            facts=tuple(h)))
        return out


LINE_KINDS = {"fact": FactLine(), "events": EventsLine(), "score": ScoreLine(), "trends": TrendsLine()}
