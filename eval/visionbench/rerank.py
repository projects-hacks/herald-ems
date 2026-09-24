"""Rerank task: the product's protocol lookup (KnowledgeBase.answer with an LLMReranker) over the qa_gold
questions, so that only the reranking model differs between runs.

The knowledge base is built exactly as the app builds it (county documents, BM25 + the configured embedder,
figure text from the product's existing cache), with no vision model attached, so the build never calls a model
and never writes the figure cache. Every model therefore reranks the same candidate passages; their fingerprint
is recorded with each run so that a changed index shows up instead of silently changing the test.

Scores (answerable questions): top1 = the reranker's first choice is the gold section; top3 = the gold section is
among its (up to 3) choices; shown_top1 = the first passage the medic would see (choices, then retrieval order).
The retrieval ceiling (gold section among the candidates at all) is the same for every model. Unanswerable
questions score a correct refusal when the product reports answerable = false.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from herald.config import Settings, load_json, load_yaml
from herald.knowledge import KnowledgeBase
from herald.knowledge.rerank import LLMReranker

from .common import ROOT, RecordingModel, is_json_error, latency, token_stats

QA = ROOT / "eval/protocols/qa_gold.jsonl"


def load_questions(path: Path = QA, only: Optional[set[str]] = None, limit: Optional[int] = None) -> list[dict]:
    rows = [json.loads(line) for line in open(path) if line.strip()]
    if only:
        rows = [r for r in rows if r["id"] in only]
    return rows[:limit] if limit else rows


def build_kb(settings: Settings) -> KnowledgeBase:
    """The app's knowledge base (herald/api/context.py wiring) minus the models: no reranker, no vision."""
    cfg = load_yaml("knowledge.yaml")
    embedder = None
    if settings.knowledge:
        from herald.models.embedder import HFEmbedder
        e = cfg["embedding"]
        embedder = HFEmbedder(e["model"], e["query_prefix"], e["device"], offline=settings.models_offline)
    county = load_json(f"counties/{settings.county}.json")
    return KnowledgeBase(county, settings.protocols_dir, cfg, embedder=embedder)


def gold_target(q: dict, county: dict) -> Optional[tuple[str, str]]:
    """(doc id, section) of the answer, mapping the key's file name to the county's document id."""
    if not q.get("doc"):
        return None
    ids = {Path(d["file"]).name: d["id"] for d in county["documents"]}
    return ids[q["doc"]], q["section"]


def _hit(p: dict, target) -> bool:
    return (p["doc"], p["section"]) == target


def candidates_fingerprint(kb: KnowledgeBase, questions: list[dict]) -> str:
    depth = kb.cfg["search"].get("rerank_depth", 8)
    ids = [[(c["doc"], c["section"], c["text"][:200]) for c in kb.search(q["q"], depth)] for q in questions]
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:12]


def ask(kb: KnowledgeBase, model: RecordingModel, q: dict) -> dict:
    depth = kb.cfg["search"].get("rerank_depth", 8)
    cands = kb.search(q["q"], depth)
    target = gold_target(q, kb.county)
    n_before = len(model.calls)
    res = kb.answer(q["q"])                              # the product path; retrieval is deterministic
    call = model.calls[-1] if len(model.calls) > n_before else None
    chosen = res["results"][:res.get("chosen", 0)] if res.get("reranked") else []
    err = res.get("error") or (call.error if call else None)
    return {"id": q["id"], "answerable_gold": target is not None, "target": target,
            "in_candidates": bool(target and any(_hit(c, target) for c in cands)),
            "chosen": [(c["doc"], c["section"]) for c in chosen],
            "shown": [(c["doc"], c["section"]) for c in res["results"]],
            "answerable": res.get("answerable"), "reranked": res.get("reranked", False),
            "top1": bool(target and chosen and _hit(chosen[0], target)),
            "top3": bool(target and any(_hit(c, target) for c in chosen[:3])),
            "shown_top1": bool(target and res["results"] and _hit(res["results"][0], target)),
            "raw": {k: v for k, v in ((call.raw if call else None) or {}).items() if not k.startswith("_")} or None,
            "ms": round(call.ms) if call else None, "error": err,
            "json_invalid": is_json_error(err, call.raw if call else None)}


def _rate(xs: list[bool]) -> Optional[float]:
    return round(sum(xs) / len(xs), 3) if xs else None


def summarize(items: list[dict], calls) -> dict:
    ans = [i for i in items if i["answerable_gold"]]
    una = [i for i in items if not i["answerable_gold"]]
    reach = [i for i in ans if i["in_candidates"]]
    return {"n": len(items), "n_answerable": len(ans), "n_unanswerable": len(una),
            "retrieval_ceiling": _rate([i["in_candidates"] for i in ans]),
            "top1": _rate([i["top1"] for i in ans]), "top3": _rate([i["top3"] for i in ans]),
            "top1_given_retrieved": _rate([i["top1"] for i in reach]),
            "shown_top1": _rate([i["shown_top1"] for i in ans]),
            "answerable_said_true": _rate([i["answerable"] is True for i in ans]),
            "refusal_on_unanswerable": _rate([i["answerable"] is False for i in una]),
            "not_reranked": sum(not i["reranked"] for i in items),
            "json_invalid": sum(i["json_invalid"] for i in items),
            "errors": sum(bool(i["error"]) and not i["json_invalid"] for i in items),
            **latency([i["ms"] for i in items if i["ms"] is not None]), **token_stats(calls)}


def run(model: RecordingModel, kb: KnowledgeBase, questions: list[dict]) -> tuple[dict, list[dict]]:
    kb.reranker = LLMReranker(model)
    items = [ask(kb, model, q) for q in questions]
    return summarize(items, [c for c in model.calls if c.ms is not None]), items
