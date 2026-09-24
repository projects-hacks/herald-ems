"""Flowchart task: the product's figure transcription of the 700-A13 stroke flowchart (a raster image with no text
layer), scored against the hand-built graph in eval/protocols/flowchart_700a13_key.json.

The transcription runs through KnowledgeBase._attach_figures itself (same page render, prompt, system text and
token limit as the app), on a knowledge-base shell whose cache folder is a fresh temporary directory, so every
run calls the model and nothing in data/ is read or written except the source PDF.

The product asks for an ordered list of steps ("If <condition> -> <next box>"), not a graph, so the scorer
matches the key against the step strings after normalization (NFKC, lowercase, every run of non-alphanumerics
becomes one space, so "GFAST 1-3" == "GFAST 1–3"):
- node recall: the node's text appears in the transcription;
- edge recall: some single step contains the edge label (if any) followed by the target node's text;
  `edge_recall_with_source` also requires the source node's text before the label;
- unsupported steps: steps that match no key edge (with or without source);
- added words: step words that appear nowhere in the key or the prompt (e.g. "primary" if the model "fixes"
  the chart from the protocol text): the transcription must copy, not interpret.
"""
from __future__ import annotations

import json
import re
import tempfile
import unicodedata
from pathlib import Path

from herald.config import Settings, load_json, load_text
from herald.knowledge import KnowledgeBase

from .common import ROOT, RecordingModel, is_json_error

KEY = ROOT / "eval/protocols/flowchart_700a13_key.json"


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", s).strip() + " "


def _find_in_order(hay: str, needles: list[str]) -> bool:
    pos = 0
    for n in needles:
        i = hay.find(n, pos)
        if i < 0:
            return False
        pos = i + len(n) - 1
    return True


def score(steps: list[str], key: dict, prompt: str = "") -> dict:
    nodes = {n["id"]: normalize(n["text"]) for n in key["nodes"]}
    norm_steps = [normalize(s) for s in steps]
    blob = " ".join(norm_steps)
    node_hits = [nid for nid, t in nodes.items() if t in blob]
    edge_hits, edge_src_hits, supported = [], [], set()
    for e in key["edges"]:
        label = [normalize(e["label"])] if e.get("label") else []
        tail = label + [nodes[e["to"]]]
        full = [i for i, s in enumerate(norm_steps) if _find_in_order(s, [nodes[e["from"]]] + tail)]
        part = [i for i, s in enumerate(norm_steps) if label and _find_in_order(s, tail)]
        if full:
            edge_src_hits.append(e)
        if full or part:
            edge_hits.append(e)
            supported |= set(full) | set(part)
    allowed = set(" ".join([*nodes.values(), *(normalize(e["label"]) for e in key["edges"] if e.get("label")),
                            normalize(prompt)]).split())
    added = sorted({w for s in norm_steps for w in s.split() if w not in allowed})
    words = [w for s in norm_steps for w in s.split()]
    ne, nn = len(key["edges"]), len(nodes)
    return {"steps": len(steps), "node_recall": round(len(node_hits) / nn, 3),
            "edge_recall": round(len(edge_hits) / ne, 3), "edge_recall_with_source": round(len(edge_src_hits) / ne, 3),
            "unsupported_steps": len(steps) - len(supported), "added_words": added,
            "added_word_rate": round(sum(w not in allowed for w in words) / len(words), 3) if words else 0.0,
            "missed_nodes": [nid for nid in nodes if nid not in node_hits],
            "missed_edges": [f"{e['from']}->{e['to']}" for e in key["edges"] if e not in edge_hits]}


def _figure_doc(settings: Settings) -> tuple[dict, dict, Path]:
    county = load_json(f"counties/{settings.county}.json")
    doc = next(d for d in county["documents"] if d.get("figures"))
    return county, doc, settings.protocols_dir / county["id"] / doc["file"]


def transcribe(model: RecordingModel, settings: Settings) -> tuple[list[str], list[dict]]:
    """The product path, uncached. Returns (steps, figure errors)."""
    county, doc, pdf = _figure_doc(settings)
    with tempfile.TemporaryDirectory(prefix="visionbench_fig_") as tmp:
        kb = KnowledgeBase.__new__(KnowledgeBase)       # a shell: no document build, no embedding
        kb.county, kb.dir, kb.vision, kb.figure_errors = county, Path(tmp), model, []
        kb._attach_figures(doc, pdf, [])
        caches = list((Path(tmp) / "index").glob("*_figure_p*.json"))
        steps = json.loads(caches[0].read_text())["steps"] if caches else []
        return steps, kb.figure_errors


def run(model: RecordingModel, settings: Settings) -> tuple[dict, list[dict]]:
    key = json.loads(KEY.read_text())
    n_before = len(model.calls)
    steps, errors = transcribe(model, settings)
    call = model.calls[-1] if len(model.calls) > n_before else None
    s = score(steps, key, load_text("prompts/figure_transcribe.md"))
    err = (errors[0]["error"] if errors else None) or (call.error if call else "no model call")
    summary = {**s, "error": err, "json_invalid": is_json_error(err, call.raw if call else None),
               "latency_ms": round(call.ms) if call else None,
               "prompt_tokens": call.usage.get("prompt_tokens") if call else None,
               "out_tokens": call.usage.get("completion_tokens") if call else None}
    return summary, [{"steps": steps, "errors": errors, **s}]
