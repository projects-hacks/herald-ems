#!/usr/bin/env python3
"""Vision-model bench: the three jobs Herald gives its vision model, each through the product's own code path,
so two served models can be compared level (same prompts, same test sets, same decoding: temperature 0,
reasoning off, as LocalLLMClient always sends).

  python eval/vision_bench.py --model omni-fp8 --runs 3 --tasks photos,flowchart,rerank
  python eval/vision_bench.py --model qwen3vl-fp8 --runs 3 --tasks photos,flowchart,rerank
  python eval/vision_bench.py --model omni --runs 1 --tasks photos --photos pulseox_01,pill_01_apixaban --warmup 0

Tasks:
  photos     eval/photos/gold.jsonl through VisionReader (herald/models/vision.py): per-fact P/R/F1 (lenient =
             printed aliases accepted, strict = LABELING_GUIDE canonical, in-prompt scope), exact-image accuracy,
             per mode, per degradation, per key, no-fact images with a false fact, JSON-invalid, latency p50/p95.
  flowchart  the 700-A13 stroke flowchart through the product's figure transcription (uncached), scored
             against eval/protocols/flowchart_700a13_key.json (nodes, edges, unsupported steps, added words).
  rerank     eval/protocols/qa_gold.jsonl through KnowledgeBase.answer with LLMReranker: top-1 / top-3 on the 22
             answerable questions, refusal on the 3 unanswerable ones, over identical retrieval candidates.

One summary line per run and task is appended to --out (eval/results.jsonl, like the other benches), each with
the hashes of the prompts and test sets (`inputs`), so a comparison is level only if those match. Per-item
details go to --dump-dir/<model>/<task>_run<k>.jsonl; the spread over runs to --dump-dir/<model>/summary.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herald.config import Settings  # noqa: E402
from herald.models import LocalLLMClient, VisionReader  # noqa: E402

from eval.visionbench import flowchart, photos, rerank  # noqa: E402
from eval.visionbench.common import RecordingModel, fingerprint, write_jsonl  # noqa: E402

TASKS = ("photos", "flowchart", "rerank")
# run-level numbers whose spread over runs is reported (per task)
SPREAD = {"photos": ("f1", "precision", "recall", "strict_f1", "in_prompt_scope_f1", "exact_image_acc",
                     "false_fact_images", "json_invalid", "latency_ms_p50", "latency_ms_p95"),
          "flowchart": ("node_recall", "edge_recall", "edge_recall_with_source", "unsupported_steps",
                        "added_word_rate", "latency_ms"),
          "rerank": ("top1", "top3", "shown_top1", "refusal_on_unanswerable", "answerable_said_true",
                     "json_invalid", "latency_ms_p50", "latency_ms_p95")}
COMPACT_DROP = {"per_key", "missed_nodes", "missed_edges"}      # kept in the dumps, left out of results.jsonl


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="served model label (ZRT --label)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tasks", default="photos,flowchart,rerank")
    ap.add_argument("--out", default="eval/results.jsonl", help="summary lines are appended here")
    ap.add_argument("--dump-dir", default="eval/dumps/vision")
    ap.add_argument("--photos", default=None, help="only these photo ids or files (comma-separated)")
    ap.add_argument("--questions", default=None, help="only these qa ids (comma-separated), e.g. qa01,qa23")
    ap.add_argument("--limit", type=int, default=None, help="only the first N photos / questions")
    ap.add_argument("--warmup", type=int, default=1, help="unscored photo calls before the first run")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds per model call")
    ap.add_argument("--note", default=None, help="free text stored with each result (e.g. the HF repo served)")
    a = ap.parse_args()
    a.tasks = [t.strip() for t in a.tasks.split(",") if t.strip()]
    unknown = set(a.tasks) - set(TASKS)
    if unknown:
        ap.error(f"unknown tasks {sorted(unknown)}; choose from {TASKS}")
    return a


def warm_up(client: LocalLLMClient, rows: list[dict], n: int) -> None:
    """Unscored calls so that the first scored call doesn't carry cold-start cost."""
    reader = VisionReader(client)
    for line in rows[:n]:
        try:
            reader.read((photos.GOLD.parent / line["file"]).read_bytes(), line["mode"])
        except Exception as e:
            print(f"warm-up call failed: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)


def result_line(a, task: str, run: int, summary: dict, extra: dict) -> dict:
    compact = {k: v for k, v in summary.items() if k not in COMPACT_DROP}
    return {"bench": f"vision:{task}", "model": a.model, "run": run, **compact, **extra,
            "inputs": fingerprint(), "note": a.note, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}


def spread(lines: list[dict]) -> dict:
    """mean / min / max over runs of each tracked number, per task."""
    out = {}
    for task in {ln["bench"].split(":")[1] for ln in lines}:
        rows = [ln for ln in lines if ln["bench"] == f"vision:{task}"]
        out[task] = {}
        for k in SPREAD[task]:
            xs = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
            if xs:
                out[task][k] = {"mean": round(statistics.mean(xs), 3), "min": min(xs), "max": max(xs), "runs": len(xs)}
    return out


def main() -> None:
    a = parse_args()
    s = Settings.from_env()
    client = LocalLLMClient(s.llm_url, a.model, timeout=a.timeout)
    if not client.available():
        sys.exit(f"'{a.model}' is not served at {s.llm_url} (served: {client.served()})")
    split = lambda v: {x.strip() for x in v.split(",") if x.strip()} if v else None
    photo_rows = photos.load_gold(only=split(a.photos), limit=a.limit) if "photos" in a.tasks else []
    questions = rerank.load_questions(only=split(a.questions), limit=a.limit) if "rerank" in a.tasks else []
    kb = rerank.build_kb(s) if questions else None
    cand_sha = rerank.candidates_fingerprint(kb, questions) if kb else None
    if a.warmup and photo_rows:
        warm_up(client, photo_rows, a.warmup)
    dump_dir = Path(a.dump_dir) / a.model
    lines = []
    for run in range(1, a.runs + 1):
        for task in a.tasks:
            model = RecordingModel(client)
            extra: dict = {}
            if task == "photos":
                summary, items = photos.run(model, photo_rows)
                rows = photos.dump_rows(items)
                extra = {"n_photos": len(photo_rows), "subset": a.photos or (f"first {a.limit}" if a.limit else None)}
            elif task == "flowchart":
                summary, rows = flowchart.run(model, s)
            else:
                summary, rows = rerank.run(model, kb, questions)
                extra = {"candidates_sha": cand_sha, "subset": a.questions or (f"first {a.limit}" if a.limit else None)}
            write_jsonl(dump_dir / f"{task}_run{run}.jsonl", rows)
            line = result_line(a, task, run, summary, extra)
            lines.append(line)
            with open(a.out, "a") as fh:
                fh.write(json.dumps(line, default=str) + "\n")
            print(json.dumps(line, default=str))
    summary = {"model": a.model, "runs": a.runs, "tasks": a.tasks, "inputs": fingerprint(), "spread": spread(lines)}
    (dump_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary["spread"], indent=1))


if __name__ == "__main__":
    main()
