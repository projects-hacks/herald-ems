#!/usr/bin/env python3
"""Run F replay slice (TRAINING_PLAN §4.4, MODEL_PLAN §0l): the base model's own answers to the other jobs the same
30B does in Herald, so the LoRA does not erode them. Self-distillation from the served FP8 of the same base
(`qwen3vl-fp8`), one request at a time; nothing here starts or stops a model.

  rerank     questions written by the model about indexed protocol passages (never the benchmark questions: they are
             dropped by 8-word runs and near-duplicates), candidates from the app's keyword retrieval, a share of them
             retrieved for a different question (so "not answerable" is represented), the exact reranker request
             (herald/knowledge/rerank.py, strict schema)
  figure     protocol pages rendered as the knowledge base renders figures (herald/knowledge/base.py), the county's
             figure prompt for figure pages and the flowchart prompt otherwise; the benchmarked flowchart is excluded
  translate  English paramedic lines from the run E v2 training set (already decontaminated against every gold set)
             to Spanish, and the model's own Spanish back to English (config/prompts/translate.yaml)

Rows are chat messages exactly as the app sends them, with the model's raw answer as the target; answers that don't
parse as the JSON the caller expects are dropped. Output: <data.replay>/train.jsonl, dev.jsonl, manifest.json.

  python scripts/build_replay_set.py            # counts from config/training.yaml herald-f.replay
  python scripts/build_replay_set.py --limit 5  # a quick look
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lora_common import ROOT  # noqa: E402


def words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", t.lower())


def runs(t: str, n: int = 8) -> set:
    w = words(t)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


class Decontaminator:
    """Drops a generated question that shares an 8-word run with a benchmark question, or whose words overlap one
    by half or more (Jaccard), or repeats an earlier generated question."""

    def __init__(self, questions: list[str], jaccard: float = 0.5):
        self.runs = set().union(*(runs(q) for q in questions)) if questions else set()
        self.sets = [set(words(q)) for q in questions]
        self.jaccard = jaccard

    def clean(self, q: str) -> bool:
        s = set(words(q))
        if not s or runs(q) & self.runs:
            return False
        if any(len(s & t) / len(s | t) >= self.jaccard for t in self.sets):
            return False
        self.runs |= runs(q)
        self.sets.append(s)
        return True


def chat(client, system: str, user: str, **kw) -> str | None:
    """The model's raw answer text (None if the call or its JSON failed)."""
    try:
        out = client.chat_json(system, user, logprobs=True, **kw)
    except Exception:
        return None
    raw = (out.get("_content") or "").strip()
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return None
    return raw


def row(task: str, rid: str, system: str, user: str, answer: str, image: str | None = None) -> dict:
    content = [{"type": "text", "text": user}, {"type": "image", "image": image}] if image else user
    return {"id": rid, "task": task, "messages": [{"role": "system", "content": system},
                                                  {"role": "user", "content": content},
                                                  {"role": "assistant", "content": answer}]}


def rerank_rows(client, kb, n: int, unanswerable: float, decon: Decontaminator, rng: random.Random) -> list[dict]:
    from herald.config import load_text
    from herald.knowledge.rerank import MAX_TOKENS, SCHEMA, LLMReranker

    reranker = LLMReranker(client)
    qprompt = load_text("prompts/replay_question.md")
    sections = [s for s in kb.sections if len(s.text) >= 200]
    rng.shuffle(sections)
    questions = []
    for s in sections:
        if len(questions) >= n:
            break
        raw = chat(client, qprompt, f"{s.doc_id} {s.number} {s.title}\n{s.text[:1200]}", max_tokens=60)
        q = json.loads(raw).get("question") if raw else None
        if isinstance(q, str) and 3 <= len(q.split()) <= 30 and decon.clean(q):
            questions.append(q)
    out = []
    depth = kb.cfg["search"].get("rerank_depth", 8)
    for i, q in enumerate(questions):
        asked = rng.choice(questions) if rng.random() < unanswerable and len(questions) > 1 else q
        passages = kb.search(asked, depth)
        user = reranker.user_message(q, passages)
        raw = chat(client, reranker.system, user, schema=SCHEMA, max_tokens=MAX_TOKENS)
        if raw:
            out.append(row("rerank", f"rr{i:04d}", reranker.system, user, raw))
    return out


def figure_rows(client, kb, n: int, per_doc: int, exclude: set, pages_dir: Path, rng: random.Random) -> list[dict]:
    from herald.config import load_text
    from herald.knowledge.base import FIGURE_DPI, FIGURE_MAX_TOKENS, FIGURE_SYSTEM
    from herald.knowledge.pdf import page_texts, render_page

    jobs = []
    for doc in kb.county["documents"]:
        path = kb.document_path(doc)
        if path is None:
            continue
        figs = {f["page"]: f.get("prompt", "prompts/figure_transcribe.md") for f in doc.get("figures", [])}
        pages = [p for p, _ in page_texts(path)]
        others = [p for p in pages if p not in figs]
        rng.shuffle(others)
        chosen = [p for p in figs if (doc["id"], p) not in exclude][:per_doc]
        chosen += others[: max(0, per_doc - len(chosen))]
        jobs += [(doc["id"], path, p, figs.get(p, "prompts/figure_transcribe.md")) for p in chosen
                 if (doc["id"], p) not in exclude]
    rng.shuffle(jobs)
    out = []
    pages_dir.mkdir(parents=True, exist_ok=True)
    for doc_id, path, page, prompt in jobs[:n]:
        png = render_page(path, page, pages_dir / f"{doc_id}_p{page}.png", dpi=FIGURE_DPI)
        user = load_text(prompt)
        raw = chat(client, FIGURE_SYSTEM, user, image_b64=base64.b64encode(png.read_bytes()).decode(),
                   max_tokens=FIGURE_MAX_TOKENS)
        if raw and isinstance(json.loads(raw).get("steps"), list):
            out.append(row("figure", f"fg_{doc_id}_p{page}", FIGURE_SYSTEM, user, raw,
                           str(png.relative_to(ROOT))))
    return out


def translate_rows(client, n: int, es_share: float, rng: random.Random) -> list[dict]:
    from herald.config import load_yaml

    t = load_yaml("prompts/translate.yaml")
    lines = [json.loads(x).get("raw_text") for x in open(ROOT / "data" / "train_e2" / "train.jsonl")]
    lines = sorted({x for x in lines if x and len(x.split()) >= 5})
    rng.shuffle(lines)
    n_es = round(n * es_share)
    out, spanish = [], []
    for i, text in enumerate(lines[: n - n_es]):
        user = t["directions"]["en_es"].replace("{text}", text)
        raw = chat(client, t["system"], user, max_tokens=t["max_tokens"])
        if raw and isinstance(json.loads(raw).get("translation"), str):
            out.append(row("translate", f"tr_en{i:04d}", t["system"], user, raw))
            spanish.append(json.loads(raw)["translation"])
    for i, text in enumerate(spanish[:n_es]):
        user = t["directions"]["es_en"].replace("{text}", text)
        raw = chat(client, t["system"], user, max_tokens=t["max_tokens"])
        if raw and isinstance(json.loads(raw).get("translation"), str):
            out.append(row("translate", f"tr_es{i:04d}", t["system"], user, raw))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="herald-f")
    ap.add_argument("--limit", type=int, default=None, help="at most this many rows per task (a quick look)")
    ap.add_argument("--tasks", default="rerank,figure,translate")
    ap.add_argument("--url", default="http://127.0.0.1:8080/v1")
    a = ap.parse_args()
    from herald.config import Settings, load_json, load_yaml
    from herald.knowledge import KnowledgeBase
    from herald.models.llm_client import LocalLLMClient

    cfg = load_yaml("training.yaml")[a.config]
    rc = cfg["replay"]
    rng = random.Random(cfg["mix"].get("seed", 13))
    client = LocalLLMClient(a.url, model=rc["teacher_label"], timeout=180)
    if not client.available():
        raise SystemExit(f"{rc['teacher_label']} is not being served at {a.url} (check `zrt status`)")
    settings = Settings()
    kb = KnowledgeBase(load_json(f"counties/{settings.county}.json"), settings.protocols_dir, load_yaml("knowledge.yaml"))
    bench = [json.loads(x)["q"] for p in rc["decontaminate"] for x in open(ROOT / p) if x.strip()]
    out_dir = ROOT / cfg["data"]["replay"]
    n = {k: min(v, a.limit) if a.limit else v for k, v in rc["tasks"].items()}
    tasks = a.tasks.split(",")
    t0, rows = time.time(), []
    if "rerank" in tasks:
        rows += rerank_rows(client, kb, n["rerank"], rc["rerank_unanswerable_share"], Decontaminator(bench), rng)
        print(json.dumps({"rerank_rows": len(rows), "s": round(time.time() - t0)}), flush=True)
    if "figure" in tasks:
        rows += figure_rows(client, kb, n["figure"], rc["figure_pages_per_doc"],
                            {tuple(x) for x in rc["exclude_pages"]}, out_dir / "pages", rng)
        print(json.dumps({"rows": len(rows), "s": round(time.time() - t0)}), flush=True)
    if "translate" in tasks:
        rows += translate_rows(client, n["translate"], rc["translate_es_to_en_share"], rng)
    rng.shuffle(rows)
    n_dev = round(len(rows) * rc["dev_share"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in (("dev", rows[:n_dev]), ("train", rows[n_dev:])):
        with open(out_dir / f"{name}.jsonl", "w") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in part)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["task"]] = counts.get(r["task"], 0) + 1
    prompts = ["prompts/protocol_rerank.md", "prompts/figure_transcribe.md", "prompts/figure_transcribe_chart.md",
               "prompts/translate.yaml", "prompts/replay_question.md"]
    manifest = {"teacher": rc["teacher_label"], "rows": counts, "dev": n_dev, "seconds": round(time.time() - t0),
                "prompt_sha256": {p: hashlib.sha256((ROOT / "config" / p).read_bytes()).hexdigest()[:16] for p in prompts}}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
