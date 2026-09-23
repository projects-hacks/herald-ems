"""The "Herald thinking" trace: what each utterance or photo did to the patient picture.

For every capture we record what was heard or seen, what each extractor produced (with confidence,
extractor, and who said it), how the checklist, scores, and alerts changed, and what the relay may
do with each fact. The UI renders this as one card per capture. Nothing here is generated prose:
it is the actual record of what the system did, so it can't drift from what really happened.
"""
from __future__ import annotations

from typing import Any

from .relay import PRIORITY
from .schema import KEYS, Fact, Status


def summarize(snap: dict) -> dict:
    """The parts of a snapshot whose change we report."""
    n, r = snap["scores"]["news2"], snap["scores"]["race"]
    return {
        "readiness": {a["id"]: {"label": a["label"], "done": a["done"], "total": a["total"], "ready": a["ready"]}
                      for a in snap["readiness"]},
        "alerts": {(a["type"], a.get("key") or a.get("label")) for a in snap["alerts"]},
        "news2": (n["score"], n["band"]) if n["complete"] else None,
        "race": (r["score"], r["positive"]) if r["complete"] else None,
        "missing": {x["key"] for x in snap["needs_attention"]["missing"] + snap["needs_attention"]["unknown"]},
    }


def diff(before: dict, after: dict) -> dict:
    out: dict[str, Any] = {"readiness": [], "alerts_new": [], "scores": [], "gaps_closed": []}
    for aid, a in after["readiness"].items():
        b = before["readiness"].get(aid)
        if b is None or b["done"] != a["done"]:
            out["readiness"].append({"label": a["label"], "from": b["done"] if b else 0, "to": a["done"],
                                     "total": a["total"], "ready": a["ready"]})
    out["alerts_new"] = [{"type": t, "label": k} for t, k in sorted(after["alerts"] - before["alerts"], key=str)]
    for name in ("news2", "race"):
        if before[name] != after[name] and after[name] is not None:
            out["scores"].append({"name": name.upper(), "from": before[name][0] if before[name] else None,
                                  "to": after[name][0], "detail": after[name][1]})
    out["gaps_closed"] = sorted(before["missing"] - after["missing"])
    return out


def fact_view(f: Fact) -> dict:
    relay = ("held: unconfirmed facts never leave the vehicle" if f.status != Status.confirmed
             else ("eligible: " + PRIORITY[f.key][1]) if f.key in PRIORITY else "stays on the vehicle (not in the ED set)")
    return {"id": f.id, "key": f.key, "label": KEYS[f.key]["label"], "value": f.value, "role": f.role.value,
            "speaker": f.speaker, "status": f.status.value, "confidence": round(f.confidence, 2),
            "extractor": f.provenance.extractor, "relay": relay}
