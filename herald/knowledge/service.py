"""Keeps the active county's knowledge base built (in the background) and in step with county switches."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from ..config import load_yaml
from .base import KnowledgeBase
from .sync import ProtocolSync


class KnowledgeService:
    def __init__(self, county_getter: Callable[[], dict], protocols_dir: Path, link_state: Callable[[], str],
                 embedder=None, reranker=None, vision=None, fetch=None, mirror: Optional[str] = None):
        self.dir, self.mirror = protocols_dir, mirror.rstrip("/") if mirror else None
        self.county_getter = lambda: self._with_mirror(county_getter())
        self.embedder, self.reranker, self.vision = embedder, reranker, vision
        self.cfg = load_yaml("knowledge.yaml")
        self.kb: Optional[KnowledgeBase] = None
        self.error: Optional[str] = None
        self._building = False
        self._lock = threading.Lock()
        self.sync = ProtocolSync(lambda: self.kb, link_state, self.cfg, fetch=fetch)

    def _with_mirror(self, county: dict) -> dict:
        """Documents without their own update URL are fetched from the configured mirror, if any."""
        if not self.mirror:
            return county
        docs = [{**d, "mirror_url": d.get("mirror_url") or f"{self.mirror}/{county['id']}/{d['id']}.pdf"}
                for d in county.get("documents", [])]
        return {**county, "documents": docs}

    @property
    def ready(self) -> bool:
        return self.kb is not None and self.kb.county["id"] == self.county_getter()["id"]

    def build(self) -> None:
        with self._lock:
            self._building = True
            try:
                self.kb = KnowledgeBase(self.county_getter(), self.dir, self.cfg, self.embedder, self.reranker, self.vision)
                self.error = None
            except Exception as e:          # the rest of Herald keeps working without protocol lookup
                self.error = str(e)[:200]
            finally:
                self._building = False

    def build_async(self) -> None:
        threading.Thread(target=self.build, daemon=True).start()

    def status(self) -> dict:
        if not self.ready:
            return {"ready": False, "building": self._building, "error": self.error}
        s = self.kb.summary()
        return {"ready": True, "county": s["county"], "sections": s["sections"], "missing": s["missing"],
                "review_required": s["review_required"], "last_sync": s["last_sync"],
                "destination_audit_ok": all(a["match"] for a in s["destination_audit"]),
                "documents": [{"id": d["id"], "title": d["title"], "effective": d["effective_in_file"] or d["effective_reviewed"]}
                              for d in s["documents"]]}
