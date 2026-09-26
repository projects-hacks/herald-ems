"""Line kinds of a handoff report. Each kind turns one line definition (config/handoff.yaml) into zero or more lines,
from confirmed facts and the snapshot's scores only. A new kind is a new class registered in kinds.LINE_KINDS; the
report builder never branches on kinds. This module holds the line model, the build context, and the fact and event
kinds; score lines are in score_line.py, trend lines in trend_line.py.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core import not_obtained as unobtainable
from ..core.schema import Fact
from ..core.vocabulary import norm_value
from ..scoring.rules import RULES, evaluate, rule_keys
from .config import HandoffConfig
from .view import ConfirmedView, template_keys


@dataclass(frozen=True)
class Line:
    kind: str                            # fact | event | score | trend | missing | empty
    text: str
    # confirmed | missing (no confirmed value) | not_obtained (the medic marked it "unable to obtain") | empty
    status: str = "confirmed"
    keys: tuple[str, ...] = ()           # the vocabulary keys (and "@<score>") this line covers
    facts: tuple[Fact, ...] = ()         # the confirmed facts it came from
    source: Optional[str] = None         # the citation behind the line (kept out of the spoken text)
    label: Optional[str] = None          # a missing line's name, for the "unable to obtain" list
    criterion: Optional[dict] = None     # a met criterion: its score, code and the source's own words


@dataclass
class BuildContext:
    view: ConfirmedView
    snapshot: dict
    scales: Any
    config: HandoffConfig
    open_checklists: set[str] = field(default_factory=set)
    trends: Any = None                   # core.trends.TrendRules: which changes are clinically meaningful
    covered: set[str] = field(default_factory=set)   # keys a line accounts for without saying anything

    def required(self, spec: dict) -> bool:
        req = spec.get("required", False)
        return bool(self.open_checklists & set(req)) if isinstance(req, list) else bool(req)

    def absent(self, spec: dict, keys: list[str], label: Optional[str] = None) -> list[Line]:
        """No confirmed value: nothing while a value waits for a tap (listed separately), "unable to obtain" when the
        medic marked it so, "not yet known" when the line is required, nothing otherwise."""
        if any(self.view.pending(k) for k in keys) or not self.required(spec):
            return []
        name = spec.get("label") or label or (self.view.vocab.label(keys[0]) if keys else "")
        if unobtainable.covers(self.view.not_obtained, keys):
            return [Line("missing", f"{name}: {self.config.words['not_obtained']}", status="not_obtained",
                         keys=tuple(keys), label=name)]
        return [Line("missing", f"{name}: {self.config.words['missing']}", status="missing", keys=tuple(keys),
                     label=name)]

    def facts(self, keys) -> tuple[Fact, ...]:
        """The confirmed facts behind these keys, in the order they were recorded."""
        order = {f.id: i for i, f in enumerate(self.view.inc.facts)}
        found = {f.id: f for k in keys if self.view.present(k) for f in self.view.facts_for(k)}
        return tuple(sorted(found.values(), key=lambda f: order[f.id]))


def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("()", "")).strip()


def bad_fields(template: str, allowed: set[str]) -> list[str]:
    used = {f for _, f, _, _ in string.Formatter().parse(template) if f is not None}
    return [f"template {template!r} uses unknown field {f!r}" for f in sorted(used - allowed)]


def unknown_keys(keys, vocabulary) -> list[str]:
    return [f"unknown key {k!r}" for k in keys if k not in vocabulary]


class FactLine:
    """The first template whose placeholders all have confirmed values. `source` is the citation kept with the line
    (not read aloud). `omit_if_same_as: <key>` drops the line when its value is the same as that key's confirmed
    value (a chief complaint that only repeats the mechanism of injury): the report says each thing once."""

    @staticmethod
    def keys(spec: dict) -> list[str]:
        return list(dict.fromkeys([k for t in spec["templates"] for k in template_keys(t)] + spec.get("keys", [])))

    def problems(self, spec, vocabulary, scales, cfg, **_) -> list[str]:
        if not spec.get("templates"):
            return ["a fact line needs templates"]
        errs = unknown_keys(self.keys(spec), vocabulary)
        if "when" in spec:
            if spec["when"].get("type") not in RULES:
                errs.append(f"unknown rule type {spec['when'].get('type')!r}")
            errs += unknown_keys(rule_keys(spec["when"]), vocabulary)
        if "omit_if_same_as" in spec:
            errs += unknown_keys([spec["omit_if_same_as"]], vocabulary)
        return errs

    @staticmethod
    def _repeats(spec: dict, ctx: BuildContext, keys: list[str]) -> bool:
        other = spec.get("omit_if_same_as")
        if not other or not keys or not ctx.view.present(other) or not ctx.view.present(keys[0]):
            return False
        return norm_value(ctx.view.values[keys[0]]) == norm_value(ctx.view.values[other])

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        keys = self.keys(spec)
        if "when" in spec and evaluate(spec["when"], ctx.view.values).met is not True:
            return []
        if self._repeats(spec, ctx, keys):
            return []
        for t in spec["templates"]:
            text = ctx.view.render(t)
            if text is not None:          # covers only what it shows: a fallback template leaves the rest a gap
                shown = list(dict.fromkeys(template_keys(t) + spec.get("keys", [])))
                return [Line("fact", text, keys=tuple(shown), facts=ctx.facts(shown), source=spec.get("source"))]
        return ctx.absent(spec, keys)


class EventsLine:
    """Every confirmed event of a record key, in the order recorded; the same event said twice is one line.
    `where` keeps only records whose fields have these values; `where_not` drops them (e.g. `before_arrival: true`
    splits what was given before the crew arrived from the crew's own treatment). A field that wasn't recorded
    matches no value."""

    def problems(self, spec, vocabulary, scales, cfg, **_) -> list[str]:
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
