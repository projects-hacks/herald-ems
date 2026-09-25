#!/usr/bin/env python3
"""Print what each stage of the stack actually returns, not just how long it took.

A timing is meaningless without its output: 0.66 s for Whisper plus a 30B extraction is fast enough to be suspicious,
and 5.4 s of vision that returns zero facts is a far worse result than 5.4 s. So this runs the same two paths as
`scripts/measure_capture_overlap.py` and prints the transcript, the facts, and the monitor reading scored against
`eval/photos/gold.jsonl`.

    scripts/run_job.py --name verify-outputs --need-gib 12 -- python scripts/verify_stack_outputs.py

Calls only the local model server and reads only local audio and photos.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def gold_for(photo: str) -> dict:
    for line in (ROOT / "eval/photos/gold.jsonl").read_text().splitlines():
        if line.strip() and json.loads(line)["file"] == photo:
            r = json.loads(line)
            return {k: v for k, v in r["facts"]}
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", default=None)
    ap.add_argument("--photo", default="monitor_01_dark.jpg")
    a = ap.parse_args()

    import soundfile as sf

    from herald.config.settings import get_settings
    from herald.core.vocabulary import default_vocabulary
    from herald.extraction.model import ModelExtractor
    from herald.models.llm_client import LocalLLMClient
    from herald.models.stt import WhisperSTT
    from herald.models.vision import VisionReader

    s = get_settings()
    clip = Path(a.clip) if a.clip else max(Path("data/audio").glob("*.wav"), key=lambda p: sf.info(p).duration)
    audio, sr = sf.read(clip)
    photo_path = ROOT / "eval/photos" / a.photo

    text_client = LocalLLMClient(s.llm_url, s.llm_model)
    vis_client = LocalLLMClient(s.llm_url, s.vision_model)
    extractor = ModelExtractor(text_client, vocabulary=default_vocabulary(), finetuned_labels=s.finetuned_models)
    reader = VisionReader(vis_client, None)
    stt = WhisperSTT(s.stt_model, offline=s.models_offline)

    print(f"extraction model: {text_client.model_name()}   vision model: {vis_client.model_name()}")
    print(f"fine-tuned profile used for extraction: {extractor.is_finetuned(text_client.model_name())}")

    # Every clip in data/audio is the same TTS test passage ("He hoped there would be stew for dinner"), which has no
    # clinical content, so extraction on it correctly returns 0 facts and its timing measures a no-op. Real EMS audio
    # does not exist in the repo (run F's ASR clips went to a gitignored temp dir). So the speech path is measured in
    # two honest pieces instead: STT on a real 10.4 s clip, because Whisper's cost tracks audio duration and not
    # content, and extraction on a real gold utterance, because its cost tracks the facts it has to emit.
    gold_rows = [json.loads(ln) for ln in (ROOT / "eval/gold_v2.jsonl").read_text().splitlines() if ln.strip()]
    busiest = max(gold_rows, key=lambda r: len(r.get("facts", [])))

    print("\nwarming both paths (excluded from every number below)")
    stt.transcribe(audio, sr)
    extractor.extract(busiest["text"])
    reader.read(photo_path.read_bytes(), "monitor", "warmup")

    print(f"\n=== A1 stt, warm, {clip.name} ({sf.info(clip).duration:.1f}s audio) ===")
    xs = []
    for i in range(3):
        t0 = time.perf_counter()
        stt.transcribe(audio, sr)
        xs.append(time.perf_counter() - t0)
        print(f"  run {i + 1}: {xs[-1]:.2f}s")
    stt_med = sorted(xs)[1]

    print(f"\n=== A2 extraction, warm, real utterance {busiest['id']} ({len(busiest['facts'])} gold facts) ===")
    print(f"  TEXT: {busiest['text'][:150]!r}")
    xs, got_facts = [], []
    for i in range(3):
        t0 = time.perf_counter()
        got_facts = extractor.extract(busiest["text"], dispatch=busiest.get("dispatch"))
        xs.append(time.perf_counter() - t0)
        print(f"  run {i + 1}: {xs[-1]:.2f}s  facts={len(got_facts)}")
    ext_med = sorted(xs)[1]
    print(f"  FACTS RETURNED ({len(got_facts)}):")
    for f in got_facts:
        print(f"    {f.key:28s} {f.value!r}")
    if not got_facts:
        print("    *** ZERO FACTS on a real utterance: this is a failure, not a fast path ***")
    print(f"\n  REAL SPEECH ROUND TRIP (warm) = stt {stt_med:.2f}s + extraction {ext_med:.2f}s "
          f"= {stt_med + ext_med:.2f}s   vs the 8-10 s clip cadence")

    # ── speech leg ────────────────────────────────────────────────────────────
    print(f"\n=== A speech: {clip.name} ({sf.info(clip).duration:.1f}s) ===")
    t0 = time.perf_counter()
    out = stt.transcribe(audio, sr)
    t_stt = time.perf_counter() - t0
    t0 = time.perf_counter()
    facts = extractor.extract(out["text"])
    t_ext = time.perf_counter() - t0
    print(f"  stt {t_stt:.2f}s   extraction {t_ext:.2f}s   total {t_stt + t_ext:.2f}s")
    print(f"  TRANSCRIPT: {out['text']!r}")
    print(f"  FACTS: {len(facts)}")
    for f in facts:
        print(f"    {f.key:28s} {f.value!r}  role={getattr(f.role, 'value', f.role)} conf={f.confidence}")
    if not facts:
        print("    *** ZERO FACTS: the timing above is a no-op, not a result ***")

    # ── vision leg, scored against gold ───────────────────────────────────────
    gold = gold_for(a.photo)
    print(f"\n=== B vision: {a.photo} (monitor mode, max_tokens 400) ===")
    t0 = time.perf_counter()
    vfacts = reader.read(photo_path.read_bytes(), "monitor", a.photo)
    t_vis = time.perf_counter() - t0
    got = {f.key: f.value for f in vfacts}
    print(f"  {t_vis:.2f}s   FACTS: {len(vfacts)}   gold has {len(gold)}")
    print(f"  {'key':28s} {'read':>10s} {'gold':>10s}")
    ok = 0
    for k in sorted(set(gold) | set(got)):
        g, r = gold.get(k, "—"), got.get(k, "MISSED")
        same = str(g) == str(r)
        ok += same
        print(f"    {k:26s} {str(r):>10s} {str(g):>10s}   {'ok' if same else 'DIFF'}")
    extra = [k for k in got if k not in gold]
    print(f"  exact: {ok}/{len(gold)}   invented keys: {extra or 'none'}")
    if not vfacts:
        print("    *** ZERO FACTS: 5 s of vision that reads nothing is worse than slow vision ***")
    elif ok == len(gold) and not extra:
        print(f"    MONITOR READ CORRECTLY: all {len(gold)} values, nothing invented.")

    print("\n" + json.dumps({"stt_s": round(t_stt, 2), "extraction_s": round(t_ext, 2),
                             "speech_total_s": round(t_stt + t_ext, 2), "speech_facts": len(facts),
                             "vision_s": round(t_vis, 2), "vision_facts": len(vfacts),
                             "vision_exact": f"{ok}/{len(gold)}", "vision_invented": len(extra)}))


if __name__ == "__main__":
    main()
