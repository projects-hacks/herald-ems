"""The county's protocol knowledge base: documents → sections → search results with citations."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import load_text, load_yaml
from .index import BM25Index
from .pdf import page_texts, render_page
from .sections import Section, SectionSplitter
from .tables import read_check_table, read_column_table


# How a protocol figure is sent to the vision model (also used for run F's replay rows: scripts/build_replay_set.py).
FIGURE_SYSTEM = "You transcribe protocol figures. Output strict JSON only."
FIGURE_MAX_TOKENS = 500
FIGURE_DPI = 150


def document_for_page(county: dict, file_name: str, page: int) -> Optional[str]:
    """The county document that holds this page of this file. One PDF can hold several documents, each with its own
    page range (AO 2025-005 holds Policy 602 on pages 12-21 and Policy 605 on pages 25-27); None for pages that no
    document covers (a redline copy, a cover memo)."""
    for d in county.get("documents", []):
        first, last = d.get("pages") or (1, float("inf"))
        if Path(d["file"]).name == file_name and first <= page <= last:
            return d["id"]
    return None


class KnowledgeBase:
    """Built from the active county's `documents` (config/counties/<id>.json) and the files under
    <data>/protocols/<county>/. Rebuilt when a document changes (sync) or the county switches."""

    def __init__(self, county: dict, protocols_dir: Path, cfg: Optional[dict] = None, embedder=None, reranker=None,
                 vision=None):
        self.cfg = cfg or load_yaml("knowledge.yaml")
        self.embedder, self.reranker, self.vision = embedder, reranker, vision
        self.county = county
        self.dir = protocols_dir / county["id"]
        self.splitter = SectionSplitter(self.cfg["heading_styles"], self.cfg["running_line_share"],
                                        self.cfg["glyph_error_pattern"], self.cfg.get("running_line_band"))
        self.sections: list[Section] = []
        self.versions: dict[str, dict] = {}
        self.missing: list[str] = []
        self.build()

    # ---------- build ----------
    def document_path(self, doc: dict) -> Optional[Path]:
        """The newest synced version if one exists, else the reviewed file named in the county config."""
        entry = self._manifest().get(doc["id"])
        current = entry.get("file") if isinstance(entry, dict) else None
        for rel in (current, doc.get("file")):
            if rel and (self.dir / rel).exists():
                return self.dir / rel
        return None

    def build(self) -> None:
        sections, versions, missing = [], {}, []
        self.figure_errors: list[dict] = []
        eff = re.compile(self.cfg["effective_pattern"])
        for doc in self.county.get("documents", []):
            path = self.document_path(doc)
            if path is None:
                missing.append(doc["id"])
                continue
            pages = page_texts(path, tuple(doc["pages"]) if doc.get("pages") else None)
            doc_sections = self.splitter.split(doc["id"], pages, doc.get("heading_style", "decimal"))
            doc_sections += self._table_sections(doc, path)
            self._attach_figures(doc, path, doc_sections)
            for sec in doc_sections:          # the document's title is context for every section in it
                sec.parents = [doc.get("title") or doc["id"], *sec.parents]
            sections += doc_sections
            m = eff.search(pages[0][1]) if pages else None
            versions[doc["id"]] = {"id": doc["id"], "title": doc.get("title"), "file": str(path.relative_to(self.dir)),
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                                   "effective_in_file": m.group(1) if m else None,
                                   "effective_date": self._calendar_date(m.group(1)) if m else None,
                                   "effective_reviewed": doc.get("effective"),
                                   "pages": doc.get("pages")}
        self.sections, self.versions, self.missing = sections, versions, missing
        self.index = BM25Index(sections, self.cfg["search"]["bm25_k1"], self.cfg["search"]["bm25_b"])
        self.vectors = self._embed_cached(sections) if self.embedder and sections else None

    def _embed_cached(self, sections: list[Section]) -> np.ndarray:
        """Vectors per document version, cached on disk (index/<doc>_<sha>_<model>_<text hash>.npy). The key includes
        the passages' text, so a changed figure transcription or splitter re-embeds instead of reusing stale vectors."""
        cache = self.dir / "index"
        cache.mkdir(parents=True, exist_ok=True)
        model = re.sub(r"[^A-Za-z0-9]+", "-", self.cfg["embedding"]["model"])
        parts = []
        for doc_id, v in self.versions.items():
            secs = [s for s in sections if s.doc_id == doc_id]
            passages = [self._passage(s) for s in secs]
            text_key = hashlib.sha256("\n\x00".join(passages).encode()).hexdigest()[:12]
            f = cache / f"{doc_id}_{v['sha256']}_{model}_{text_key}.npy"
            if f.exists():
                vec = np.load(f)
            else:
                vec = self.embedder.embed(passages)
                np.save(f, vec)
            parts.append(vec)
        return np.concatenate(parts)

    def _calendar_date(self, printed: str) -> Optional[str]:
        """The printed effective date as YYYY-MM-DD ("January 1, 2026" and "1/1/2026" are the same date)."""
        for fmt in self.cfg.get("effective_formats", []):
            try:
                return datetime.strptime(" ".join(printed.split()), fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _passage(s: Section) -> str:
        return " > ".join(s.parents) + "\n" + s.text

    def _table_sections(self, doc: dict, path: Path) -> list[Section]:
        """Tables read as data (e.g. Policy 602 Table B), one citable section per row and per facility."""
        out, legends = [], {}
        self.tables = getattr(self, "tables", {})
        for t in doc.get("tables", []):
            if t["reader"] == "columns":
                rows = read_column_table(path, t["page"], t["header"], t["fields"])
                legends[t["id"]] = {r["id"]: r for r in rows}
                self.tables[(doc["id"], t["id"])] = {"title": t["title"], "page": t["page"], "rows": rows}
            elif t["reader"] == "check_glyph":
                grid = read_check_table(path, t["page"], t["glyph"])
                legend = legends.get(t.get("legend"), {})
                name = lambda i: f"{legend[i]['facility']} ({i})" if i in legend else i
                self.tables[(doc["id"], t["id"])] = {"title": t["title"], "page": t["page"], **grid}
                for r in grid["rows"]:
                    out.append(Section(doc["id"], t["id"], f"{t['id']}: {r['label']}", t["page"], 1,
                                       f"{t['id']} ({t['title']}), {r['label']}: " +
                                       (", ".join(name(i) for i in r["checked"]) or "none")))
                for col in grid["columns"]:
                    services = [r["label"] for r in grid["rows"] if col in r["checked"]]
                    out.append(Section(doc["id"], t["id"], f"{t['id']}: {name(col)}", t["page"], 1,
                                       f"{t['id']} ({t['title']}), {name(col)}: " + (", ".join(services) or "none")))
        return out

    def _attach_figures(self, doc: dict, path: Path, sections: list[Section]) -> None:
        """Charts that exist only as images: the local vision model transcribes each once per document version
        (cached per document version and vision model, so switching models re-reads the figure), and the text joins
        its section, labeled as read from the image. The numbered text governs. A figure that is not a flowchart names
        its own prompt (`prompt` in the county's document entry)."""
        reader = re.sub(r"[^A-Za-z0-9]+", "-", (self.vision.model_name() if self.vision is not None else None) or "none")
        for fig in doc.get("figures", []):
            sha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            cache = self.dir / "index" / f"{doc['id']}_{sha}_figure_p{fig['page']}_{reader}.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            steps = json.loads(cache.read_text())["steps"] if cache.exists() else None
            if steps is None and self.vision is not None:
                try:            # a figure that can't be read leaves the rest of the knowledge base working
                    import base64
                    png = render_page(path, fig["page"], cache.parent / f"{doc['id']}_{sha}_p{fig['page']}.png",
                                      dpi=FIGURE_DPI)
                    data = self.vision.chat_json(FIGURE_SYSTEM,
                                                 load_text(fig.get("prompt", "prompts/figure_transcribe.md")),
                                                 image_b64=base64.b64encode(png.read_bytes()).decode(),
                                                 max_tokens=FIGURE_MAX_TOKENS)
                    steps = [str(x) for x in data.get("steps", [])][:30]
                    cache.write_text(json.dumps({"steps": steps, "page": fig["page"]}, indent=1))
                except Exception as e:
                    self.figure_errors.append({"doc": doc["id"], "page": fig["page"], "error": str(e)[:160]})
                    continue
            if not steps:
                continue
            target = next((s for s in sections if s.number == fig["section"]), None)
            text = (f"[{fig['title']}, page {fig['page']}, read from the image by the local vision model; "
                    f"the numbered sections govern] " + " ".join(steps))
            if target:
                target.text += "\n" + text
            else:
                sections.append(Section(doc["id"], fig["section"], fig["title"], fig["page"], 1, text))

    def audit_destinations(self) -> list[dict]:
        """Compare the county config's reviewed destination lists with the current document's table."""
        dest = self.county.get("destinations", {})
        a = dest.get("audit")
        table = getattr(self, "tables", {}).get((a["document"], a["table"])) if a else None
        if not table:
            return []
        rows = {r["label"]: r["checked"] for r in table.get("rows", [])}
        out = []
        for cfg_key, service in a["services"].items():
            in_doc, in_cfg = sorted(rows.get(service, [])), sorted(dest.get(cfg_key, []))
            out.append({"service": service, "document": sorted(in_doc), "config": in_cfg, "match": in_doc == in_cfg,
                        "only_in_document": sorted(set(in_doc) - set(in_cfg)),
                        "only_in_config": sorted(set(in_cfg) - set(in_doc))})
        return out

    # ---------- queries ----------
    def ranked(self, query: str, depth: int = 50) -> list[tuple[float, Section]]:
        """Keyword (BM25) and semantic ranks fused by reciprocal rank; keyword only without an embedder."""
        kw = self.index.search(query, depth)
        if self.vectors is None:
            return kw
        q = self.embedder.embed([query], query=True)[0]
        sims = self.vectors @ q
        dense = [(float(sims[i]), self.sections[i]) for i in np.argsort(-sims)[:depth]]
        kf = self.cfg["embedding"]["fusion_k"]
        fused: dict[int, float] = {}
        for ranking in (kw, dense):
            for r, (_, s) in enumerate(ranking):
                fused[id(s)] = fused.get(id(s), 0.0) + 1.0 / (kf + r + 1)
        by_id = {id(s): s for s in self.sections}
        return sorted(((v, by_id[i]) for i, v in fused.items()), key=lambda x: -x[0])

    def answer(self, query: str, k: Optional[int] = None) -> dict:
        """Retrieval, then (if a reranker is wired) the local model picks which passages answer the question."""
        k = k or self.cfg["search"]["top_k"]
        candidates = self.search(query, self.cfg["search"].get("rerank_depth", 8))
        if not self.reranker or not candidates:
            return {"query": query, "answerable": None, "results": candidates[:k], "reranked": False}
        try:
            order, answerable = self.reranker.rerank(query, candidates)
        except Exception as e:
            return {"query": query, "answerable": None, "results": candidates[:k], "reranked": False, "error": str(e)[:120]}
        picked = [candidates[i] for i in order]
        rest = [c for i, c in enumerate(candidates) if i not in order]
        return {"query": query, "answerable": answerable, "results": (picked + rest)[:k], "reranked": True,
                "chosen": len(picked)}

    def search(self, query: str, k: Optional[int] = None) -> list[dict]:
        out = []
        for score, s in self.ranked(query)[: k or self.cfg["search"]["top_k"]]:
            v = self.versions.get(s.doc_id, {})
            out.append({"doc": s.doc_id, "title": v.get("title"), "section": s.number, "heading": s.title,
                        "page": s.page, "text": s.text, "parents": s.parents, "score": round(score, 3),
                        "effective": v.get("effective_in_file") or v.get("effective_reviewed"),
                        "text_layer_uncertain": s.uncertain})
        return out

    def summary(self) -> dict:
        m = self._manifest()
        return {"county": self.county["id"], "documents": list(self.versions.values()), "missing": self.missing,
                "sections": len(self.sections), "destination_audit": self.audit_destinations(),
                "figure_errors": getattr(self, "figure_errors", []),
                "review_required": [d for d, e in m.items() if isinstance(e, dict) and e.get("review_required")],
                "last_sync": m.get("_last_sync")}

    def page_image(self, doc_id: str, page: int, cache_dir: Path) -> Path:
        doc = next(d for d in self.county["documents"] if d["id"] == doc_id)
        path = self.document_path(doc)
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / f"{self.county['id']}_{doc_id}_{self.versions[doc_id]['sha256']}_p{page}.png"
        return out if out.exists() else render_page(path, page, out)

    # ---------- versions (written by sync) ----------
    def _manifest(self) -> dict:
        """The sync manifest, or {} if it is absent, empty or half-written.

        This is read on the GET /api/state path via summary(), so a parse error here becomes a 500 on the screen the
        medic is looking at. It existing is not enough: the file is rewritten while the protocol index builds on first
        start, so a read can land on a truncated or zero-length file. On 2026-09-25 that produced
        `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` from /api/state during app startup -- the manifest
        existed and was empty. A missing manifest and an unreadable one mean the same thing to every caller (no sync
        information yet), and the fields built from it are optional, so degrade instead of failing the whole snapshot.
        """
        p = self.dir / "manifest.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text()) or {}
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}

    def export(self) -> list[dict]:
        return [asdict(s) for s in self.sections]
