"""Protocol updates when connected: each document with a `mirror_url` (the agency's update feed, or the demo
mirror) is checked with a conditional request, only while the relay measures a good link.

A changed file is stored as a new version next to the old one, the index is rebuilt, and the document is marked
`review_required`: the county config (checklists, scales, destinations) is reviewed data and is never rewritten
by a document update. A person clears the flag (POST /api/protocols/{doc}/reviewed) after checking it."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import httpx

Fetch = Callable[[str, dict], httpx.Response]


def _http_fetch(url: str, headers: dict, timeout: float = 20.0) -> httpx.Response:
    return httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)


class ProtocolSync:
    def __init__(self, kb_getter: Callable, link_state: Callable[[], str], cfg: dict,
                 fetch: Optional[Fetch] = None, clock: Callable[[], float] = time.time):
        self.kb_getter, self.link_state, self.cfg = kb_getter, link_state, cfg["sync"]
        self.fetch = fetch or (lambda url, h: _http_fetch(url, h, self.cfg["timeout_s"]))
        self.clock = clock
        self.last_run = 0.0
        self.last_result: Optional[dict] = None

    def due(self) -> bool:
        if self.clock() - self.last_run < self.cfg["interval_s"]:
            return False
        need = self.cfg.get("only_when_link")
        return not need or self.link_state() in (need, "not configured")

    def run(self, force: bool = False) -> Optional[dict]:
        if not force and not self.due():
            return None
        self.last_run = self.clock()
        kb = self.kb_getter()
        manifest_path = kb.dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        checked, updated, errors = 0, [], []
        for doc in kb.county.get("documents", []):
            url = doc.get("mirror_url")
            if not url:
                continue
            checked += 1
            entry = manifest.get(doc["id"], {})
            headers = {k: v for k, v in (("If-None-Match", entry.get("etag")),
                                         ("If-Modified-Since", entry.get("last_modified"))) if v}
            try:
                r = self.fetch(url, headers)
            except Exception as e:
                errors.append({"doc": doc["id"], "error": str(e)[:120]})
                continue
            if r.status_code == 304:
                continue
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                errors.append({"doc": doc["id"], "error": f"HTTP {r.status_code}, not a PDF"})
                continue
            sha = hashlib.sha256(r.content).hexdigest()
            current = kb.document_path(doc)
            if current is not None and hashlib.sha256(current.read_bytes()).hexdigest() == sha:
                entry.update(etag=r.headers.get("etag"), last_modified=r.headers.get("last-modified"))
                manifest[doc["id"]] = entry
                continue
            rel = Path("versions") / f"{doc['id']}_{sha[:12]}.pdf"
            (kb.dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (kb.dir / rel).write_bytes(r.content)
            manifest[doc["id"]] = {"file": str(rel), "sha256": sha[:16], "etag": r.headers.get("etag"),
                                   "last_modified": r.headers.get("last-modified"),
                                   "fetched_at": datetime.now(timezone.utc).isoformat(),
                                   "previous_file": str(current.relative_to(kb.dir)) if current else None,
                                   "review_required": True}
            updated.append(doc["id"])
        manifest["_last_sync"] = datetime.now(timezone.utc).isoformat()
        kb.dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2))
        if updated:
            kb.build()
        self.last_result = {"checked": checked, "updated": updated, "errors": errors, "at": manifest["_last_sync"]}
        return self.last_result

    @staticmethod
    def mark_reviewed(kb, doc_id: str) -> dict:
        path = kb.dir / "manifest.json"
        manifest = json.loads(path.read_text()) if path.exists() else {}
        if doc_id not in manifest:
            raise KeyError(doc_id)
        manifest[doc_id]["review_required"] = False
        manifest[doc_id]["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(manifest, indent=2))
        return manifest[doc_id]
