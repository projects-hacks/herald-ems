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
        self.max_chars: int = cfg.get("max_chars", 700)
        self._kb, self._county = kb, county
        self._results: dict[tuple[str, str], dict] = {}
        self._inflight: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    # ---------- which situations are live ----------
    def active(self, snap: dict) -> list[dict]:
        alerts = {a.get("type") for a in snap.get("alerts", [])}
        checklists = {r.get("id") for r in snap.get("readiness", [])}
        return [c for c in self.cues
                if alerts & set(c["when"].get("alerts", [])) or checklists & set(c["when"].get("checklists", []))]

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
                out.append({"id": c["id"], "title": c["title"], "query": c["query"],
                            **(r if r else {"state": "searching", "passages": []})})
        return out
