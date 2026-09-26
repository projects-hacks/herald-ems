"""The plain-text rendering of a handoff report, for reading aloud on the radio or at the bedside. Deterministic:
the same report always gives the same text."""
from __future__ import annotations

from typing import Optional

from .informants import informants_sentence


def _sentence(parts: list[str], sep: str) -> str:
    text = sep.join(p.rstrip(".") for p in parts if p)
    return f"{text}." if text else ""


def render_text(report: dict, words: dict, informant_words: Optional[dict] = None) -> str:
    sep = words["line_separator"]
    out = [f"{report['format']['title']}."]
    for s in report["sections"]:
        body = _sentence([ln["text"] for ln in s["lines"]], sep)
        if body:
            out.append(body if not s.get("say_label", True) else f"{s['label']}: {body}")
    if informant_words and report.get("informants"):
        out.append(informants_sentence(report["informants"], informant_words, sep, words["list_separator"]))
    if report["not_yet_known"]:
        out.append(f"{words['missing_heading']}: " + _sentence([g["text"] for g in report["not_yet_known"]], sep))
    apart = [x["label"] for x in report.get("not_obtained", []) if not x.get("inline")]
    if apart:                     # a line already saying "unable to obtain" is not repeated here
        out.append(f"{words['not_obtained_heading']}: " + _sentence(apart, sep))
    if report["not_yet_confirmed"]:
        names = [u["label"] + (f" ({words['differs']})" if u["differs"] else "") for u in report["not_yet_confirmed"]]
        out.append(f"{words['unconfirmed_heading']}: " + _sentence(names, sep))
    return "\n".join(out)
