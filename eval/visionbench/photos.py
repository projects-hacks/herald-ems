"""Photo task: every gold image through the product's VisionReader (same prompts, same filters as the app)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from herald.config import load_yaml
from herald.models import VisionReader

from .common import ROOT, RecordingModel, is_json_error, latency, token_stats
from .photo_scoring import aggregate, score_item, strength_ok

GOLD = ROOT / "eval/photos/gold.jsonl"


def load_gold(path: Path = GOLD, only: Optional[set[str]] = None, limit: Optional[int] = None) -> list[dict]:
    rows = [json.loads(line) for line in open(path) if line.strip()]
    if only:
        rows = [r for r in rows if r["file"] in only or Path(r["file"]).stem in only]
    return rows[:limit] if limit else rows


def read_one(reader: VisionReader, model: RecordingModel, line: dict) -> dict:
    """One image through the reader. The reader's output (after its plausibility filters) is what is scored;
    the model's parsed JSON is kept alongside for error analysis."""
    image = (GOLD.parent / line["file"]).read_bytes()
    n_before = len(model.calls)
    err, facts = None, []
    try:
        facts = reader.read(image, line["mode"], photo_id=line["file"])
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:200]}"
    call = model.calls[-1] if len(model.calls) > n_before else None
    raw = call.raw if call else None
    return {"pred": [[f.key, f.value] for f in facts],
            "texts": [f.provenance.text for f in facts if f.provenance and f.provenance.text],
            "raw": {k: v for k, v in (raw or {}).items() if not k.startswith("_")} or None,
            "ms": call.ms if call else None, "usage": call.usage if call else {}, "error": err or (call and call.error),
            "json_invalid": is_json_error(err or (call and call.error), raw)}


def run(model: RecordingModel, rows: list[dict]) -> tuple[dict, list[dict]]:
    """Returns (summary, per-image records)."""
    reader = VisionReader(model)
    prompts = load_yaml("prompts/vision.yaml")["modes"]
    items = []
    for line in rows:
        r = read_one(reader, model, line)
        items.append({"file": line["file"], "line": line, **r,
                      "score": score_item(line, r["pred"], prompts[line["mode"]]),
                      "strength_ok": strength_ok(line.get("strength"), r["texts"])})
    calls = [c for c in model.calls if c.ms is not None]
    summary = {**aggregate(items), **latency([i["ms"] for i in items if i["ms"] is not None]), **token_stats(calls)}
    return summary, items


def dump_rows(items: list[dict]) -> list[dict]:
    return [{"file": i["file"], "mode": i["line"]["mode"], "degradations": i["line"]["degradations"],
             "gold": i["line"]["facts"], "pred": i["pred"], "raw": i["raw"], "ms": round(i["ms"] or 0),
             "usage": i["usage"], "error": i["error"], "exact": i["score"]["exact"],
             "extra": i["score"]["lenient"]["extra"], "missed": i["score"]["lenient"]["missed"],
             "strict_missed": i["score"]["strict"]["missed"], "strength_ok": i["strength_ok"]} for i in items]
