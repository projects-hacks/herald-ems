"""Situational protocol lookup: the copilot finds the county passage for the situation it recognises.

The situation comes from deterministic state (open checklists, positive screens, county alerts); the query for each
situation is configuration (config/protocol_cues.yaml); the passage comes from the county's own documents through the
same retrieval + local reranker as the protocol search screen. Nothing here writes clinical text: a cue shows the
document's words, its citation and effective date, or says the documents do not cover it.

Searches run off the request path (AppContext's lifespan loop calls `pending` and `resolve`); `view` only reads the
cache, so building the snapshot never waits on a model.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from ..config import load_yaml


def _cut(text: str, limit: int) -> tuple[str, bool]:
    """Shorten at a sentence boundary so a quote never ends mid-word; report whether it was shortened."""
    if len(text) <= limit:
        return text, False
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("; "), head.rfind(".\n"))
    return (head[: stop + 1] if stop > limit // 2 else head.rsplit(" ", 1)[0]).rstrip() + " …", True


class ProtocolCues:
    def __init__(self, kb: Callable[[], Optional[object]], county: Callable[[], str], config: Optional[dict] = None):
        cfg = config or load_yaml("protocol_cues.yaml")
        self.cues: list[dict] = cfg["cues"]
        self.passages: int = cfg.get("passages", 2)
        req = cfg.get("requests", {})
        # longest phrase first, so "show me the protocol for" wins over its tail "protocol for"
        self.phrases: list[str] = sorted((p.lower() for p in req.get("phrases", [])), key=len, reverse=True)
        self.keep: int = req.get("keep", 3)
        self.asked: dict[str, list[dict]] = {}              # incident id -> the medic's own requests, newest first
        self.max_chars: int = cfg.get("max_chars", 700)
        self._kb, self._county = kb, county
        self._results: dict[tuple[str, str], dict] = {}
        self._inflight: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    # ---------- the medic asking ----------
    def ask(self, incident_id: str, text: str) -> Optional[dict]:
        """If the words ask for a protocol, remember the request for this patient; the lookup runs like any cue."""
        said = re.sub(r"\s+", " ", text).strip()
        low = said.lower()
        for phrase in self.phrases:
            i = low.find(phrase)
            if i < 0:
                continue
            topic = re.split(r"[.,;!?]", said[i + len(phrase):], maxsplit=1)[0].strip(" :\"'“”")   # the topic ends with the clause
            topic = re.sub(r"^(a|an|the)\s+", "", topic, flags=re.I)
            if len(topic) < 3:
                return None
            cue = {"id": f"asked:{topic.lower()}", "title": f"You asked: {topic}", "query": topic, "asked": True,
                   "at": datetime.now(timezone.utc).isoformat()}
            with self._lock:
                mine = [c for c in self.asked.get(incident_id, []) if c["id"] != cue["id"]]
                self.asked[incident_id] = [cue, *mine][: self.keep]
            return cue
        return None

    # ---------- which situations are live ----------
    def active(self, snap: dict) -> list[dict]:
        alerts = {a.get("type") for a in snap.get("alerts", [])}
        checklists = {r.get("id") for r in snap.get("readiness", [])}
        asked = self.asked.get((snap.get("incident") or {}).get("id", ""), [])
        out, seen = list(asked), {c["query"].lower() for c in asked}
        for c in self.cues:
            if "from_facts" in c:                  # any presentation: the heard value is the query
                for key in c["from_facts"]:
                    fact = (snap.get("facts") or {}).get(key) or {}
                    values = fact.get("value") if isinstance(fact.get("value"), list) else [fact.get("value")]
                    for v in values:
                        if isinstance(v, str) and len(v.strip()) > 2 and fact.get("status") != "rejected" and v.lower() not in seen:
                            seen.add(v.lower())
                            out.append({"id": f"{c['id']}:{v.lower()}", "title": v.strip().capitalize(), "query": v.strip()})
            elif alerts & set(c["when"].get("alerts", [])) or checklists & set(c["when"].get("checklists", [])):
                out.append(c)
        return out

    def _key(self, cue: dict) -> tuple[str, str]:
        return (self._county(), cue["id"])

    def pending(self, snap: dict) -> list[dict]:
        """Active cues with no result yet and no search running; the caller resolves them off the request path."""
        if self._kb() is None:
            return []
        with self._lock:
            out = [c for c in self.active(snap) if self._key(c) not in self._results and self._key(c) not in self._inflight]
            self._inflight.update(self._key(c) for c in out)
        return out

    def resolve(self, cue: dict) -> None:
        key = self._key(cue)
        try:
            kb = self._kb()
            answer = kb.answer(cue["query"], self.passages) if kb is not None else None
            result = self._result(answer) if answer is not None else None
            if result is not None:
                result["found_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:                                   # a model hiccup must not lose the cue for good
            result = {"state": "unavailable", "error": f"{type(e).__name__}: {e}"[:160]}
        with self._lock:
            self._inflight.discard(key)
            if result is not None and result["state"] != "unavailable":
                self._results[key] = result

    def _result(self, answer: dict) -> dict:
        if answer.get("answerable") is False:
            return {"state": "not_covered", "passages": []}
        chosen = answer.get("chosen") or (1 if answer.get("results") else 0)
        passages = []
        for r in answer.get("results", [])[: min(self.passages, max(chosen, 1))]:
            text, shortened = _cut(re.sub(r"\s+", " ", r["text"]).strip(), self.max_chars)   # PDF line breaks are layout, not meaning
            passages.append({"doc": r["doc"], "title": r.get("title"), "section": r["section"], "heading": r.get("heading"),
                             "page": r.get("page"), "effective": r.get("effective"), "text": text, "shortened": shortened,
                             "text_layer_uncertain": r.get("text_layer_uncertain", False)})
        return {"state": "found" if passages else "not_covered", "passages": passages, "reranked": answer.get("reranked", False)}

    # ---------- what the screen shows ----------
    def view(self, snap: dict) -> list[dict]:
        if self._kb() is None:
            return []
        out = []
        with self._lock:
            for c in self.active(snap):
                r = self._results.get(self._key(c))
                out.append({"id": c["id"], "title": c["title"], "query": c["query"], "asked": c.get("asked", False),
                            **(r if r else {"state": "searching", "passages": []})})
        return out
