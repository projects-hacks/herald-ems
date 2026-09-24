#!/usr/bin/env python3
"""Protocol retrieval bench without the reranker: eval/protocols/qa_gold.jsonl through KnowledgeBase.search, the
product's own retrieval, in two modes. No model server is called.

  bm25    keyword search only (the fallback when no embedder is wired)
  hybrid  BM25 + the configured embedder (config/knowledge.yaml `embedding`, on the CPU), reciprocal-rank fusion;
          what the app ranks before the local model reranks

  python eval/bench_protocols.py                          # both modes, summary to stdout
  python eval/bench_protocols.py --modes bm25 --runs 3 --dump eval/dumps/protocols/retrieval.jsonl

Scores over the answerable questions (quote and table_lookup): top1 / top3 / top5 = the cited (document, section)
is among the first k passages; in_rerank_depth = among the `rerank_depth` passages the reranker chooses from (its
ceiling); doc_top1 = the first passage is from the right document. Unanswerable questions need the reranker's
refusal, so they are only counted here. The first 25 questions cover the 5 documents indexed before 2026-09-24
(`v1`); the rest cover the documents added then (`added`). The section embeddings are cached per document version
in the protocols folder, like the app's.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herald.config import Settings, load_json, load_yaml  # noqa: E402
from herald.knowledge import KnowledgeBase  # noqa: E402

from eval.visionbench.rerank import QA, gold_target, load_questions  # noqa: E402

V1 = 25          # qa01-qa25: the original set


def build(mode: str, settings: Settings) -> KnowledgeBase:
    cfg = load_yaml("knowledge.yaml")
    embedder = None
    if mode == "hybrid":
        from herald.models.embedder import HFEmbedder
        e = cfg["embedding"]
        embedder = HFEmbedder(e["model"], e["query_prefix"], e["device"], offline=settings.models_offline)
    return KnowledgeBase(load_json(f"counties/{settings.county}.json"), settings.protocols_dir, cfg, embedder=embedder)


def score(kb: KnowledgeBase, questions: list[dict]) -> list[dict]:
    depth = kb.cfg["search"].get("rerank_depth", 8)
    out = []
    for q in questions:
        target = gold_target(q, kb.county)
        ranked = [(r["doc"], r["section"]) for r in kb.search(q["q"], max(depth, 5))]
        rank = next((i + 1 for i, r in enumerate(ranked) if r == target), None) if target else None
        out.append({"id": q["id"], "category": q["category"], "target": target, "rank": rank, "top": ranked[:3],
                    "doc_top1": bool(target and ranked and ranked[0][0] == target[0])})
    return out


def summarize(items: list[dict], depth: int) -> dict:
    ans = [i for i in items if i["target"]]
    rate = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    hit = lambda k: [i["rank"] is not None and i["rank"] <= k for i in ans]
    return {"n_answerable": len(ans), "n_unanswerable": len(items) - len(ans),
            "top1": rate(hit(1)), "top3": rate(hit(3)), "top5": rate(hit(5)), "in_rerank_depth": rate(hit(depth)),
            "doc_top1": rate([i["doc_top1"] for i in ans]),
            "hits": {"top1": sum(hit(1)), "top3": sum(hit(3)), "top5": sum(hit(5)), "in_rerank_depth": sum(hit(depth))}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", default="bm25,hybrid")
    ap.add_argument("--runs", type=int, default=1, help="repeat to confirm the ranking is deterministic")
    ap.add_argument("--questions", default=str(QA))
    ap.add_argument("--dump", default=None, help="per-question ranks (JSON lines)")
    a = ap.parse_args()
    settings = Settings.from_env()
    questions = load_questions(Path(a.questions))
    dump = []
    for mode in a.modes.split(","):
        kb = build(mode, settings)
        depth = kb.cfg["search"].get("rerank_depth", 8)
        runs = []
        for run in range(a.runs):
            t = time.time()
            items = score(kb, questions)
            runs.append(items)
            ms = round(1000 * (time.time() - t) / len(questions), 1)
            res = {"mode": mode, "run": run + 1, "documents": len(kb.versions), "sections": len(kb.sections),
                   "all": summarize(items, depth),
                   "v1": summarize([i for i, q in zip(items, questions) if int(q["id"][2:]) <= V1], depth),
                   "added": summarize([i for i, q in zip(items, questions) if int(q["id"][2:]) > V1], depth),
                   "ms_per_query": ms}
            print(json.dumps(res))
            dump += [{"mode": mode, "run": run + 1, **i} for i in items]
        same = all([i["rank"] for i in r] == [i["rank"] for i in runs[0]] for r in runs)
        print(json.dumps({"mode": mode, "runs": a.runs, "identical_ranks_across_runs": same}))
    if a.dump:
        Path(a.dump).parent.mkdir(parents=True, exist_ok=True)
        Path(a.dump).write_text("".join(json.dumps(d, default=str) + "\n" for d in dump))


if __name__ == "__main__":
    main()
