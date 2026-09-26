"""Score lines of a handoff report: a score from the snapshot, said the way a paramedic hands it over.

A complete score is one short line ("NEWS2 9, high risk"); an incomplete score says nothing (its missing inputs are
listed where they are required, never as score bookkeeping); a criteria score says each met criterion as a short
spoken phrase from config/handoff.yaml `criteria_say`, with the values that decided it. The source's own words and
the citation stay on the line's JSON (`criterion`, `source`), out of the spoken text. No partial total is ever shown
(AGENTS.md invariant 6).
"""
from __future__ import annotations

from typing import Any, Optional

from .lines import BuildContext, Line, bad_fields, tidy, unknown_keys
from .view import template_keys

SCORE_FIELDS = {"name", "score", "band", "level", "max", "cite", "missing"}
HIT_FIELDS = SCORE_FIELDS | {"group", "text", "say"}


def for_score(value: Any, sid: str, default: Any = None) -> Any:
    """A line option given once for every score, or per score id ({trauma_605: ..., field_triage: ...})."""
    if isinstance(value, dict):
        return value.get(sid, default)
    return default if value is None else value


def criterion_ids(scale) -> list[tuple[str, str]]:
    """(group id, criterion id) for every criterion, in the order of a result's `criteria` rows: its `code`, or
    "<group>.<n>" (1-based) for a source that does not letter its criteria."""
    return [(g["id"], c.get("code") or f"{g['id']}.{i + 1}")
            for g in scale.groups for i, c in enumerate(scale.d.get(g["id"], []))]


def say_problems(sid: str, scale, cfg, vocabulary) -> list[str]:
    """Every criterion of a criteria score read in a report needs its spoken wording, and nothing else may be there."""
    say = cfg.criteria_say.get(sid)
    if say is None:
        return [f"criteria_say: no wording for {sid}"]
    ids = [cid for _, cid in criterion_ids(scale)]
    errs = [f"criteria_say.{sid}: no wording for criterion {cid!r}" for cid in ids if cid not in say]
    errs += [f"criteria_say.{sid}: unknown criterion {cid!r}" for cid in say if cid not in ids]
    for cid, templates in say.items():
        errs += [f"criteria_say.{sid}.{cid}: {e}" for t in templates
                 for e in unknown_keys(template_keys(t), vocabulary)]
    return errs


class ScoreLine:
    """Options: `score` (an id, or a list: the first one the active county has); `only_if` (met | positive) with
    `template` (once, or per score id); `name` (the spoken name, once or per score id); `cite` (the short citation,
    kept on the line, once or per score id); `group_names` (a criteria group's spoken name, once or per score id);
    `cover_incomplete` (an incomplete score also accounts for its checklist item, so the item is not listed again as
    "not yet known": its inputs are)."""

    def problems(self, spec, vocabulary, scales, cfg, **_) -> list[str]:
        ids = spec["score"] if isinstance(spec["score"], list) else [spec["score"]]
        errs = [f"unknown score {s!r}" for s in ids if s not in scales]
        if spec.get("only_if"):
            t = spec.get("template")
            if not t:
                errs.append("only_if needs a template")
            for one in (t.values() if isinstance(t, dict) else [t] if t else []):
                errs += bad_fields(one, SCORE_FIELDS)
        for s in ids:
            if s not in scales:
                continue
            kind = scales[s].d["kind"]
            if kind not in cfg.score_text:
                errs.append(f"no score_text for kind {kind!r}")
            for name, t in (cfg.score_text.get(kind) or {}).items():
                errs += bad_fields(t or "", HIT_FIELDS if name == "hit" else SCORE_FIELDS)
            if kind == "criteria" and not spec.get("only_if"):
                errs += say_problems(s, scales[s], cfg, vocabulary)
        return errs

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        ids = spec["score"] if isinstance(spec["score"], list) else [spec["score"]]
        sid = next((s for s in ids if s in ctx.snapshot["scores"]), None)
        if sid is None:
            return []
        r, scale = ctx.snapshot["scores"][sid], ctx.scales[sid]
        if r.get("applies") is False:
            return []
        cite = for_score(spec.get("cite"), sid, "")
        inputs = sorted(scale.input_keys())
        fields = {"name": for_score(spec.get("name"), sid, scale.name), "score": r.get("score"),
                  "band": r.get("band"), "level": r.get("level"), "max": getattr(scale, "max_score", None),
                  "cite": cite, "missing": ", ".join(r.get("missing", []))}

        def line(text: str, facts=None, criterion: Optional[dict] = None) -> Line:
            return Line("score", tidy(text), keys=(f"@{sid}",), facts=ctx.facts(inputs) if facts is None else facts,
                        source=r.get("source"), criterion=criterion)

        if spec.get("only_if"):
            template = for_score(spec["template"], sid)
            return [line(template.format(**fields))] if template and r.get(spec["only_if"]) is True else []
        if not any(ctx.view.present(k) for k in inputs):
            return ctx.absent(spec, inputs, label=scale.name)
        words = ctx.config.score_text[scale.d["kind"]]
        if scale.d["kind"] == "criteria":
            hits = self._criteria(spec, ctx, sid, r, scale, words, fields, line)
            if hits:
                return hits
            return self._said(words.get("not_met" if r["complete"] else "undecided"), spec, ctx, sid, fields, line)
        return self._said(words.get("complete" if r["complete"] else "incomplete"), spec, ctx, sid, fields, line)

    @staticmethod
    def _said(template: Optional[str], spec: dict, ctx: BuildContext, sid: str, fields: dict, line) -> list[Line]:
        """The score's line, or nothing when its wording is left empty (score bookkeeping is never read aloud)."""
        if template:
            return [line(template.format(**fields))]
        if spec.get("cover_incomplete"):
            ctx.covered.add(f"@{sid}")
        return []

    @staticmethod
    def _criteria(spec, ctx: BuildContext, sid, r, scale, words, fields, line) -> list[Line]:
        names = spec.get("group_names") or {}
        names = names[sid] if isinstance(names.get(sid), dict) else names
        say = ctx.config.criteria_say.get(sid, {})
        rows = list(zip(criterion_ids(scale), scale.criteria_keys(), r["criteria"]))
        out = []
        for g in scale.groups:
            met = [(cid, keys) for (gid, cid), (_, keys), row in rows if gid == g["id"] and row["state"] == "met"]
            group = names.get(g["id"], g.get("short", g["id"]))
            for hit, (cid, keys) in zip(r[g["id"]], met):
                spoken = next((t for t in map(ctx.view.render, say.get(cid, [])) if t is not None), None) or hit
                criterion = {"score": sid, "code": cid, "text": hit, "cite": f"{fields['cite']} {cid}".strip()}
                out.append(line(words["hit"].format(**fields, group=group, text=hit, say=spoken),
                                ctx.facts(sorted(keys)), criterion))
        return out
