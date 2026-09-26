"""Trend lines of a handoff report: a vital that moved, said the way it is handed over ("HR rising, 118 → 142").

Only a clinically meaningful change is read: the key needs a change rule in config/trends.yaml (the same rules the
cabin alerts use), and some earlier confirmed reading and a later one must differ by that rule. The wording (short
labels, direction words, how many readings) is content in config/handoff.yaml. Confirmed readings only.
"""
from __future__ import annotations

from ..core.vocabulary import norm_value
from .lines import BuildContext, Line, bad_fields, unknown_keys

DIRECTIONS = ("up", "down", "flat")


def _points(history: list, max_points: int | None) -> list:
    """The readings to say: a run of the same value is said once; past `max_points`, the first, the latest, and
    between them the readings furthest from the first (in the order taken)."""
    runs = history[:1]
    for f in history[1:]:
        if norm_value(f.value) != norm_value(runs[-1].value):
            runs.append(f)
    if not max_points or len(runs) <= max_points:
        return runs
    first, middle = runs[0], runs[1:-1]
    keep = {f.id for f in sorted(middle, key=lambda f: -abs(f.value - first.value))[:max(max_points - 2, 0)]}
    return [first, *(f for f in middle if f.id in keep), runs[-1]]


class TrendsLine:
    """Options: `keys`; `template` ({label} {direction} {series}); `point_template` ({value}, {time} HH:MM);
    `labels` (a short spoken label per key, else the vocabulary label); `directions` (up, down, flat: latest against
    first); `max_points`."""

    def problems(self, spec, vocabulary, scales, cfg, trends=None, **_) -> list[str]:
        errs = unknown_keys(spec.get("keys", []), vocabulary) + unknown_keys(spec.get("labels", {}), vocabulary)
        errs += bad_fields(spec["template"], {"label", "direction", "series"}) if spec.get("template") \
            else ["needs template"]
        errs += bad_fields(spec.get("point_template", "{value}"), {"value", "time"})
        errs += [f"directions: missing {d!r}" for d in DIRECTIONS if d not in (spec.get("directions") or {})]
        if trends is not None:
            errs += [f"{k} has no change rule in config/trends.yaml" for k in spec.get("keys", [])
                     if k not in trends.rules]
        return errs

    def build(self, spec: dict, ctx: BuildContext) -> list[Line]:
        v, rules, out = ctx.view, ctx.trends, []
        for key in spec["keys"]:
            h = v.history(key)
            if rules is None or key not in rules.rules or len(h) < 2:
                continue
            values = [f.value for f in h]
            if not any(rules.significant(key, a, b) for i, a in enumerate(values) for b in values[i + 1:]):
                continue
            direction = "up" if values[-1] > values[0] else "down" if values[-1] < values[0] else "flat"
            point = spec.get("point_template", "{value}")
            series = ctx.config.words["arrow"].join(
                point.format(value=v.value_text(key, f.value, f.ts), time=v.clock(f.provenance.observed_at or f.ts))
                for f in _points(h, spec.get("max_points")))
            label = (spec.get("labels") or {}).get(key) or v.vocab.label(key)
            out.append(Line("trend", spec["template"].format(label=label, direction=spec["directions"][direction],
                                                             series=series), keys=(key,), facts=tuple(h)))
        return out
