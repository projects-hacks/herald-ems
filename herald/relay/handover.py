"""The final "handed over" packet and its delivery status.

At the hospital the medic taps Hand over once; the incident then carries `handed_over_at` and the handoff report
frozen at that moment (`handoff_final`). The relay sends that frozen report to the ED as one last packet per patient,
through the same sequenced, acknowledged, retried path as every other packet.

What leaves the vehicle is the report's section labels and line texts (built from confirmed facts only) and the
listed gaps. The report's `not_yet_confirmed` list and its read-aloud `text` (which names unconfirmed items) stay on
the vehicle: only confirmed facts reach the ED (AGENTS.md invariant 4).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _parse(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def is_handed_over(inc) -> bool:
    return bool(getattr(inc, "handed_over_at", None) and getattr(inc, "handoff_final", None))


def final_report_body(inc) -> dict:
    """The wire form of the frozen report (`ho` in the packet)."""
    report = inc.handoff_final
    fmt = report.get("format", {})
    return {
        "at": _iso(inc.handed_over_at),
        "format": fmt.get("id"), "title": fmt.get("title") or fmt.get("label"),
        "sections": [{"label": section.get("label"), "lines": [line.get("text") for line in section.get("lines", [])]}
                     for section in report.get("sections", [])],
        "not_yet_known": [gap.get("text") or gap.get("label") for gap in report.get("not_yet_known", [])],
    }


def handover_status(inc, delivered: Optional[dict], acknowledgements: list[dict]) -> Optional[dict]:
    """{"at", "delivered_at", "received_at"} for a handed-over patient, else None.

    `delivered_at`: when the ED acknowledged the final packet. `received_at`: the first clinician acknowledgement
    the ED recorded at or after the hand over."""
    at = getattr(inc, "handed_over_at", None)
    if at is None:
        return None
    received = None
    for row in acknowledgements or []:
        when = _parse(row.get("at"))
        if when is not None and when.tzinfo is not None and when >= at:
            received = row.get("at")
            break
    return {"at": _iso(at), "delivered_at": (delivered or {}).get("delivered_at"), "received_at": received}
