"""Who told us what: the handoff report's sources, grouped by who gave the information ("husband: medications,
allergies"; "patient monitor: heart rate, SpO2"; "medic: the rest").

Built only from the confirmed facts behind the report's own lines, so it never names a source for something the
report does not say. Who a fact came from is its provenance: the monitor for a camera reading of the patient monitor,
the medic, the patient, or the person the check step read it as from the words ("husband"); a room-mic fact whose
speaker the words did not show is listed as not identified. The wording is config/handoff.yaml `informants`.
"""
from __future__ import annotations

from ..core.vocabulary import Vocabulary

# the order a report reads its sources in: people other than the crew first (that is what the ED cannot see), then
# the devices, then the crew, and what could not be attributed last
_ORDER = {"family": 0, "bystander": 0, "patient": 1, "device": 2, "photo": 3, "medic": 4, "unknown": 5}


def _who(source: dict, words: dict) -> tuple[str, str]:
    """(group id, how the report names them) for one fact's source."""
    role = source.get("role") or "unknown"
    if role in ("family", "bystander") and source.get("speaker"):
        return f"{role}:{source['speaker']}", str(source["speaker"])
    return role, words["labels"].get(role, role)


def informants(sections: list[dict], vocab: Vocabulary, words: dict) -> list[dict]:
    """[{"who", "role", "keys", "items"}] in reading order; `items` are the vocabulary labels of what they told."""
    groups: dict[str, dict] = {}
    for section in sections:
        for line in section.get("lines", []):
            if line.get("status") != "confirmed":
                continue
            for src in line.get("sources", []):
                gid, who = _who(src, words)
                g = groups.setdefault(gid, {"who": who, "role": src.get("role") or "unknown", "keys": []})
                if src["key"] not in g["keys"]:
                    g["keys"].append(src["key"])
    out = sorted(groups.values(), key=lambda g: _ORDER.get(g["role"], 0))
    for g in out:
        items: list[str] = []
        for key in g["keys"]:
            label = vocab.label(key) if key in vocab else key
            if label not in items:
                items.append(label)
        g["items"] = items
    return out


def informants_sentence(rows: list[dict], words: dict, sep: str, list_sep: str) -> str:
    """"Who told us: husband: medications, allergies; patient monitor: heart rate; medic: the rest." When someone
    other than the crew told something, the crew's own long list is read as "the rest"."""
    if not rows:
        return ""
    others = any(r["role"] != "medic" for r in rows)
    parts = [f"{r['who']}: {words['rest'] if r['role'] == 'medic' and others else list_sep.join(r['items']).lower()}"
             for r in rows]
    return f"{words['heading']}: {sep.join(parts)}."
