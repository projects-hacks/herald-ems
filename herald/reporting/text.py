"""The plain-text rendering of a handoff report, for reading aloud on the radio or at the bedside. Deterministic:
the same report always gives the same text."""
from __future__ import annotations


def _sentence(parts: list[str], sep: str) -> str:
    text = sep.join(p.rstrip(".") for p in parts if p)
    return f"{text}." if text else ""


def render_text(report: dict, words: dict) -> str:
    sep = words["line_separator"]
    out = [f"{report['format']['title']}."]
    for s in report["sections"]:
        body = _sentence([ln["text"] for ln in s["lines"]], sep)
        if body:
            out.append(body if not s.get("say_label", True) else f"{s['label']}: {body}")
    if report["not_yet_known"]:
        out.append(f"{words['missing_heading']}: " + _sentence([g["text"] for g in report["not_yet_known"]], sep))
    if report["not_yet_confirmed"]:
        names = [u["label"] + (f" ({words['differs']})" if u["differs"] else "") for u in report["not_yet_confirmed"]]
        out.append(f"{words['unconfirmed_heading']}: " + _sentence(names, sep))
    return "\n".join(out)
