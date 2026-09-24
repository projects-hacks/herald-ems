"""Criterion rule types for criteria scores (config/scores/*.yaml, `kind: criteria`) and for checklist conditions.

A rule reads confirmed values and returns an `Outcome`: met (True), not met (False), or undecided (None) because an
input it needs is missing. A missing input is never guessed (AGENTS.md invariant 6). Each rule type is one small
function registered in RULES; a new type is a new function, never a branch inside the engine. Thresholds, keys and
wording come from the definition; nothing clinical is written here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Outcome:
    met: Optional[bool]                      # None: undecided, an input is missing
    fields: dict = field(default_factory=dict)          # the values that decided it, for the criterion's text
    needs: tuple = ()                        # keys whose absence left it undecided
    override: dict = field(default_factory=dict)        # band-specific code/text/label (sbp_by_age)
    parts: tuple = ()                        # (rule, Outcome) pairs of nested rules (count_at_least, all_of, any_of)


Rule = Callable[[dict, dict[str, Any]], Outcome]


def _norm(x: Any) -> str:
    return str(x).strip().lower()


def _empty(x: Any) -> bool:
    return x is None or x == "" or x == []


def _missing(*keys: str) -> Outcome:
    return Outcome(None, needs=tuple(keys))


def _compare(c: dict, v: dict, test: Callable[[Any], bool]) -> Outcome:
    x = v.get(c["key"])
    return _missing(c["key"]) if x is None else Outcome(test(x), {"value": x})


def _below(c, v):
    """value < threshold"""
    return _compare(c, v, lambda x: x < c["value"])


def _above(c, v):
    """value > threshold"""
    return _compare(c, v, lambda x: x > c["value"])


def _outside(c, v):
    """value < low or value > high"""
    return _compare(c, v, lambda x: x < c["low"] or x > c["high"])


def _between(c, v):
    """low <= value <= high; either bound may be left out"""
    return _compare(c, v, lambda x: c.get("low", x) <= x <= c.get("high", x))


def _room_air_below(c, v):
    """SpO2 below a threshold while breathing room air; undecided on oxygen (the room-air value is unknown)."""
    x, o2 = v.get(c["key"]), v.get(c["oxygen_key"])
    if x is None:
        return _missing(c["key"])
    if o2 is None:
        return _missing(c["oxygen_key"])
    if o2:
        return Outcome(None, {"value": x}, needs=(c["key"],))
    return Outcome(x < c["value"], {"value": x})


def _sbp_by_age(c, v):
    """Systolic BP below an age-banded limit; each band carries its own code and text."""
    age, sbp = v.get(c["age_key"]), v.get(c["sbp_key"])
    if age is None or sbp is None:
        return _missing(*[k for k, x in ((c["age_key"], age), (c["sbp_key"], sbp)) if x is None])
    for b in c["bands"]:
        if b.get("age_min", age) <= age <= b.get("age_max", age):
            limit = b["sbp_below"] if "sbp_below" in b else b["sbp_below_base"] + b["sbp_below_per_year"] * age
            over = {k: b[k] for k in ("code", "text", "label") if k in b}
            return Outcome(sbp < limit, {"sbp": sbp, "limit": limit, "age": age}, override=over)
    return Outcome(False, {"sbp": sbp, "age": age})


def _hr_above_sbp(c, v):
    """Heart rate greater than systolic BP, from a minimum age; below that age the criterion does not apply."""
    keys = (c["age_key"], c["sbp_key"], c["hr_key"])
    age, sbp, hr = (v.get(k) for k in keys)
    if None in (age, sbp, hr):
        return _missing(*[k for k in keys if v.get(k) is None])
    if age < c["min_age"]:
        return Outcome(False, {"hr": hr, "sbp": sbp, "age": age})
    return Outcome(hr > sbp, {"hr": hr, "sbp": sbp, "age": age})


def _motor_gcs_below(c, v):
    """Motor GCS below a threshold. Without a stated motor score, the stated GCS total bounds it by arithmetic
    (motor = total - eye - verbal, each within its published range); a total that doesn't settle it is undecided."""
    m = v.get(c["key"])
    if m is not None:
        return Outcome(m < c["value"], {"value": m})
    total = v.get(c["total_key"])
    if total is None:
        return _missing(c["key"])
    lo = max(c["motor_min"], total - c["others_max"])
    hi = min(c["motor_max"], total - c["others_min"])
    if hi < c["value"]:
        return Outcome(True, {"value": f"at most {hi} (GCS total {total})"})
    if lo >= c["value"]:
        return Outcome(False, {"value": f"{lo} (GCS total {total})"})
    return Outcome(None, {"value": f"{lo}-{hi} (GCS total {total})"}, needs=(c["key"],))


def _present(c, v):
    """The key has a non-empty value that is not one of the definition's negative words (`unless`)."""
    x = v.get(c["key"])
    if _empty(x):
        return _missing(c["key"])
    negatives = {_norm(w) for w in c.get("unless", ())}
    items = x if isinstance(x, list) else [x]
    kept = [i for i in items if _norm(i) not in negatives]
    return Outcome(bool(kept), {"value": ", ".join(str(i) for i in kept) if kept else x})


def _present_prefix(c, v):
    """Any key starting with the prefix has a value (e.g. a stroke exam has started)."""
    hit = next((k for k, x in v.items() if k.startswith(c["prefix"]) and not _empty(x)), None)
    return Outcome(True, {"value": hit}) if hit else Outcome(None)


def _contains(c, v):
    """A list key holds the given value. A value not described is undecided, never 'absent'."""
    hit = next((x for x in v.get(c["key"]) or [] if _norm(x) == _norm(c["value"])), None)
    return Outcome(True, {"value": hit}) if hit is not None else _missing(c["key"])


def _one_of(c, v):
    """A single value is one of the listed values (case-insensitive)."""
    x = v.get(c["key"])
    return _missing(c["key"]) if _empty(x) else Outcome(_norm(x) in {_norm(w) for w in c["values"]}, {"value": x})


def _record_has(c, v):
    """A record key (e.g. meds.given) holds a record whose field is one of the listed values."""
    allowed = {_norm(w) for w in c["values"]}
    hit = next((r for r in v.get(c["key"]) or [] if isinstance(r, dict) and _norm(r.get(c["field"])) in allowed), None)
    return Outcome(True, {"value": hit[c["field"]]}) if hit else _missing(c["key"])


def _count(rules: list, v: dict, n: int) -> Outcome:
    parts = tuple((r, evaluate(r, v)) for r in rules)
    met = sum(o.met is True for _, o in parts)
    unknown = sum(o.met is None for _, o in parts)
    state = True if met >= n else (False if met + unknown < n else None)
    needs = tuple(k for _, o in parts if o.met is None for k in o.needs)
    return Outcome(state, {"count": met, "n": n, "total": len(parts), "unknown": unknown},
                   needs=needs if state is None else (), parts=parts)


def _count_at_least(c, v):
    """At least n of the nested rules are met (decided as soon as the answer can't change)."""
    return _count(c["rules"], v, c["n"])


def _all_of(c, v):
    return _count(c["rules"], v, len(c["rules"]))


def _any_of(c, v):
    return _count(c["rules"], v, 1)


RULES: dict[str, Rule] = {
    "below": _below, "above": _above, "outside": _outside, "between": _between,
    "room_air_below": _room_air_below, "sbp_by_age": _sbp_by_age, "hr_above_sbp": _hr_above_sbp,
    "motor_gcs_below": _motor_gcs_below, "present": _present, "present_prefix": _present_prefix,
    "contains": _contains, "one_of": _one_of, "record_has": _record_has,
    "count_at_least": _count_at_least, "all_of": _all_of, "any_of": _any_of,
}


def evaluate(rule: dict, values: dict[str, Any]) -> Outcome:
    return RULES[rule["type"]](rule, values)


def rule_keys(rule: dict) -> set[str]:
    """Every vocabulary key a rule reads (for validation and the UI contract)."""
    keys = {rule[k] for k in ("key", "oxygen_key", "total_key", "age_key", "sbp_key", "hr_key") if k in rule}
    for r in rule.get("rules", ()):
        keys |= rule_keys(r)
    return keys
