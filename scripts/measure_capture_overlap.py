#!/usr/bin/env python3
"""Can the mic and the camera run at the same time on one served model?

The product direction is that the camera watches the patient monitor continuously WHILE the mic listens
continuously. `config/capture.yaml` currently sets `rate.skip_while_speech: true`, so the capture scheduler defers
every frame while speech is being processed. Ambient clips arrive about every 8 s and monitor intents expire after
`window_s: 6`, so if one speech round trip takes longer than the gap between clips, speech is never idle, the camera
never reads, and the intents expire into a decision history no screen shows.

`skip_while_speech` is Herald's choice, not a server limit: vLLM batches concurrent requests. This measures what the
overlap actually costs, so the choice is made on numbers:

  A  speech   one STT + extraction round trip on an ~8 s ambient clip, wall clock
  B  vision   one monitor-mode read at max_tokens 400, wall clock
  C  both     the same two, fired concurrently

If C is not much worse than max(A, B), one 30B can serve both and `skip_while_speech` can go. If C is far worse, or
if B alone exceeds `monitor.min_interval_s` (15 s, the floor between monitor reads), continuous monitor vision needs
its own served model — the seam already exists as `HERALD_KNOWLEDGE_MODEL` (TRAINING_PLAN §7a).

    scripts/run_job.py --name measure-overlap --need-gib 12 -- python scripts/measure_capture_overlap.py --runs 3

Reads nothing but local audio and photos, and calls only the local model server.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def stats(name: str, xs: list[float]) -> dict:
    xs = sorted(xs)
    return {"stage": name, "runs": len(xs), "median_s": round(statistics.median(xs), 2),
            "min_s": round(xs[0], 2), "max_s": round(xs[-1], 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=3, help="HARD RULE 3: a deciding number is measured 3 times")
    ap.add_argument("--clip", default=None, help="a ~8 s wav (default: the longest under data/audio)")
    ap.add_argument("--photo", default="eval/photos/monitor_01_dark.jpg")
    ap.add_argument("--max-tokens", type=int, default=400, help="informational: VisionReader fixes it at 400")
    a = ap.parse_args()

    import soundfile as sf

    from herald.config import load_yaml
    from herald.config.settings import get_settings
    from herald.extraction.model import ModelExtractor
    from herald.core.vocabulary import default_vocabulary
    from herald.models.llm_client import LocalLLMClient
    from herald.models.stt import WhisperSTT
    from herald.models.vision import VisionReader

    s = get_settings()
    cap = load_yaml("capture.yaml")
    clip = Path(a.clip) if a.clip else max(Path("data/audio").glob("*.wav"), key=lambda p: sf.info(p).duration)
    audio, sr = sf.read(clip)
    photo = Path(a.photo).read_bytes()
    print(json.dumps({"clip": clip.name, "clip_s": round(sf.info(clip).duration, 1), "photo": a.photo,
                      "extraction_model": s.llm_model, "vision_model": s.vision_model,
                      "skip_while_speech": cap["rate"].get("skip_while_speech"),
                      "monitor_min_interval_s": cap["monitor"]["min_interval_s"],
                      "monitor_intent_window_s": 6}, indent=1), flush=True)

    text_client = LocalLLMClient(s.llm_url, s.llm_model)
    vis_client = LocalLLMClient(s.llm_url, s.vision_model)
    vocab = default_vocabulary()
    extractor = ModelExtractor(text_client, vocabulary=vocab, finetuned_labels=s.finetuned_models)
    reader = VisionReader(vis_client, None)
    stt = WhisperSTT(s.stt_model, offline=s.models_offline)

    def speech() -> float:
        t0 = time.perf_counter()
        out = stt.transcribe(audio, sr)
        extractor.extract(out["text"])
        return time.perf_counter() - t0

    def vision() -> float:
        t0 = time.perf_counter()
        reader.read(photo, "monitor", "measure")      # VisionReader hardcodes max_tokens=400, the real budget
        return time.perf_counter() - t0

    print("warming both paths (excluded from the numbers)", flush=True)
    speech(), vision()

    rows = []
    for label, fn in (("A speech (STT + extraction)", speech), ("B vision (monitor, max_tokens 400)", vision)):
        xs = []
        for i in range(a.runs):
            xs.append(fn())
            print(f"  {label} run {i + 1}: {xs[-1]:.2f}s", flush=True)
        rows.append(stats(label, xs))

    both_speech, both_vision, both_wall = [], [], []
    for i in range(a.runs):
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(2) as ex:
            fs, fv = ex.submit(speech), ex.submit(vision)
            sp, vi = fs.result(), fv.result()
        wall = time.perf_counter() - t0
        both_speech.append(sp), both_vision.append(vi), both_wall.append(wall)
        print(f"  C concurrent run {i + 1}: wall {wall:.2f}s (speech {sp:.2f}s, vision {vi:.2f}s)", flush=True)
    rows += [stats("C concurrent wall", both_wall), stats("C speech leg", both_speech),
             stats("C vision leg", both_vision)]

    print()
    for r in rows:
        print(json.dumps(r), flush=True)

    a_med, b_med, c_med = rows[0]["median_s"], rows[1]["median_s"], rows[2]["median_s"]
    verdict = {
        "serial_if_deferred_s": round(a_med + b_med, 2),
        "concurrent_s": c_med,
        "overlap_cost_vs_slowest_alone_s": round(c_med - max(a_med, b_med), 2),
        "vision_alone_exceeds_min_interval": b_med > cap["monitor"]["min_interval_s"],
        "speech_exceeds_ambient_gap_8s": a_med > 8,
    }
    verdict["one_model_serves_both"] = (not verdict["vision_alone_exceeds_min_interval"]
                                       and c_med < a_med + b_med)
    print("\n" + json.dumps(verdict, indent=1))


if __name__ == "__main__":
    main()
