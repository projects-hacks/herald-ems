"""The "Herald thinking" trace: what each capture did to the patient picture.

For every capture: what was heard or seen, what each extractor produced (confidence, extractor, who said it),
how the checklist, scores, and alerts changed, and what the relay may do with each fact. Nothing here is
generated prose: it is the record of what the system did.
"""
from __future__ import annotations

from typing import Any

from ..core.schema import Fact, Status
from ..core.vocabulary import Vocabulary
from ..relay import RelayTiers

SCORE_KEYS = ("news2", "race", "gfast")     # snapshot["scores"] entries whose changes the trace reports


class TraceRecorder:
    def __init__(self, vocabulary: Vocabulary, tiers: RelayTiers):
        self.vocab, self.tiers = vocabulary, tiers

    def summarize(self, snap: dict) -> dict:
        """The parts of a snapshot whose change we report."""
        scores = {}
        for sid in SCORE_KEYS:
            s = snap["scores"].get(sid)
            if s and s.get("complete"):
                scores[sid] = (s["score"], s["band"] if "band" in s else s.get("positive"))
            else:
                scores[sid] = None
        return {
            "readiness": {a["id"]: {"label": a["label"], "done": a["done"], "total": a["total"], "ready": a["ready"]}
                          for a in snap["readiness"]},
            "alerts": {(a["type"], a.get("key") or a.get("label")) for a in snap["alerts"]},
            "scores": scores,
            "missing": {x["key"] for x in snap["needs_attention"]["missing"] + snap["needs_attention"]["unknown"]},
        }

    @staticmethod
    def diff(before: dict, after: dict) -> dict:
        out: dict[str, Any] = {"readiness": [], "alerts_new": [], "scores": [], "gaps_closed": []}
        for aid, a in after["readiness"].items():
            b = before["readiness"].get(aid)
            if b is None or b["done"] != a["done"]:
                out["readiness"].append({"label": a["label"], "from": b["done"] if b else 0, "to": a["done"],
                                         "total": a["total"], "ready": a["ready"]})
        out["alerts_new"] = [{"type": t, "label": k} for t, k in sorted(after["alerts"] - before["alerts"], key=str)]
        for name, now in after["scores"].items():
            was = before["scores"].get(name)
            if was != now and now is not None:
                out["scores"].append({"name": name.upper(), "from": was[0] if was else None, "to": now[0],
                                      "detail": now[1]})
        out["gaps_closed"] = sorted(before["missing"] - after["missing"])
        return out

    def fact_view(self, f: Fact) -> dict:
        if f.status != Status.confirmed:
            relay = "held: unconfirmed facts never leave the vehicle"
        elif f.key in self.tiers:
            relay = "eligible: " + self.tiers.why(f.key)
        else:
            relay = "stays on the vehicle (not in the ED set)"
        return {"id": f.id, "key": f.key, "label": self.vocab.label(f.key), "value": f.value, "role": f.role.value,
                "speaker": f.speaker, "status": f.status.value, "confidence": round(f.confidence, 2),
                "extractor": f.provenance.extractor, "relay": relay, "hold_reason": f.provenance.hold_reason}
