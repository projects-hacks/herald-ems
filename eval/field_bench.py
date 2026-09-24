#!/usr/bin/env python3
"""Field robustness benchmark (docs/TASK_SPECS.md S8): people's own-words recordings of the fact cards, through the
product's speech-to-text (Whisper) and extractor, scored against the cards with the benchmark's atoms.

  python eval/field_bench.py --model ems-d-fp8 --runs 3
  python eval/field_bench.py --model ems-d-fp8 --runs 3 --omissions data/field_audio/omissions.jsonl

Speech-to-text runs once per clip (greedy decoding) and is cached next to the audio; the extractor runs --runs
times, called exactly as the app calls it (the card's mic, speaker and dispatch). Reported per run: headline
precision/recall/F1 (the gold-v2 definition, so it sits next to the held-out numbers), F1 over every key on the
cards, role accuracy, quiet vs noise, 95% intervals (clips; speakers as clusters), and the paired quiet-minus-noise
difference; per key: precision/recall pooled over runs.

Scoring is "as carded": a fact the speaker forgot to say counts as a miss. After run 1, a review file lists each
clip's transcript and missed facts; a person moves the facts the speaker really never said into "omitted" and
passes it back with --omissions. The "said" score is then reported beside the as-carded one, never instead of it.

Outputs: one summary line per run in --out (eval/results.jsonl); the spread over runs and the per-key table in
eval/dumps/field_v1/<model>_summary.json; per-clip details (they contain transcripts, i.e. what people said) and
the review file under data/field_audio/_bench/, which is gitignored like the audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from eval.field.cards import Card, load_cards  # noqa: E402
from eval.field.manifest import Manifest  # noqa: E402
from eval.field.scoring import ClipScore, fact_id, score_clip  # noqa: E402
from eval.field.stats import bootstrap_f1, cluster_bootstrap_f1, paired_difference, prf  # noqa: E402
from herald.core.schema import source_role  # noqa: E402

AUDIO = ROOT / "data" / "field_audio"


def clip_key(c: dict) -> tuple[str, str, str]:
    return c["speaker"], c["card"], c["condition"]


def load_clips(manifest: Path, cards: dict[str, Card], root: Path = ROOT) -> list[dict]:
    clips, missing = [], []
    for row in Manifest(manifest).rows():
        if row["card"] not in cards:
            raise SystemExit(f"manifest names card {row['card']}, which is not in the cards file")
        path = Path(row["file"]) if Path(row["file"]).is_absolute() else root / row["file"]
        (clips if path.exists() else missing).append({**row, "path": path})
    if missing:
        raise SystemExit(f"{len(missing)} clips in the manifest have no audio file, e.g. {missing[0]['file']}")
    return clips


def transcribe(clips: list[dict], stt, cache_path: Path) -> dict[tuple, dict]:
    """(speaker, card, condition) -> {"text", "ms"}; cached by audio hash and speech-to-text model."""
    import soundfile as sf
    cache = {}
    if cache_path.exists():
        cache = {r["key"]: r for r in map(json.loads, cache_path.read_text().splitlines()) if r}
    out = {}
    for c in clips:
        raw = c["path"].read_bytes()
        key = f"{stt.model}:{hashlib.sha1(raw).hexdigest()}"
        if key not in cache:
            audio, sr = sf.read(c["path"], dtype="float32")
            t0 = time.perf_counter()
            text = stt.transcribe(audio, sr)["text"]
            cache[key] = {"key": key, "speaker": c["speaker"], "text": text,
                          "ms": round((time.perf_counter() - t0) * 1000)}
        out[clip_key(c)] = cache[key]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("".join(json.dumps(r) + "\n" for r in cache.values()))
    return out


def extract(clips: list[dict], cards: dict[str, Card], transcripts: dict, extractor) -> dict[tuple, dict]:
    """The extractor on each transcript, called as the app calls it (herald/api/capture.py)."""
    out = {}
    for c in clips:
        card = cards[c["card"]]
        text = transcripts[clip_key(c)]["text"]
        t0, err, pred = time.perf_counter(), None, []
        if text:
            try:
                facts = extractor.extract(text, card.by, source_role(card.by, card.speaker), card.speaker,
                                          dispatch=card.dispatch)
                pred = [(f.key, f.value, f.role.value) for f in facts]
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:200]}"
        out[clip_key(c)] = {"pred": pred, "ms": (time.perf_counter() - t0) * 1000, "error": err}
    return out


def load_omissions(path: Path | None) -> dict[tuple, set[str]]:
    if not path:
        return {}
    out = {}
    for r in map(json.loads, Path(path).read_text().splitlines()):
        if r and r.get("omitted"):
            out[(r["speaker"], r["card"], r["condition"])] = {fact_id(f[0], f[1]) for f in r["omitted"]}
    return out


def aggregate(clips: list[dict], scores: dict[tuple, ClipScore], conditions: list[str]) -> dict:
    """Headline and all-keys numbers with intervals, by condition, and the paired condition difference."""
    def counts(part: str, keys) -> list[tuple[int, int, int]]:
        return [tuple(getattr(scores[k], part)[:3]) for k in keys]

    keys = [clip_key(c) for c in clips]
    tp, fp, fn, role_ok = (sum(scores[k].headline[i] for k in keys) for i in range(4))
    p, r, f1 = prf(tp, fp, fn)
    by_speaker = defaultdict(list)
    for k in keys:
        by_speaker[k[0]].append(k)
    out = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3),
           "role_acc": round(role_ok / tp, 3) if tp else 0.0, "counts": {"tp": tp, "fp": fp, "fn": fn},
           "ci95_clips": bootstrap_f1(counts("headline", keys)),
           "ci95_speakers": cluster_bootstrap_f1({s: counts("headline", ks) for s, ks in by_speaker.items()})}
    at, af, an = (sum(scores[k].all_keys[i] for k in keys) for i in range(3))
    out["all_keys"] = {"f1": round(prf(at, af, an)[2], 3), "ci95_clips": bootstrap_f1(counts("all_keys", keys))}
    out["by_condition"] = {}
    for cond in conditions:
        ck = [k for k in keys if k[2] == cond]
        if ck:
            ct = [sum(scores[k].headline[i] for k in ck) for i in range(3)]
            out["by_condition"][cond] = {"clips": len(ck), "f1": round(prf(*ct)[2], 3),
                                         "ci95_clips": bootstrap_f1(counts("headline", ck))}
    if len(conditions) >= 2:
        a, b = conditions[:2]
        pairs = [(tuple(scores[(s, c, a)].headline[:3]), tuple(scores[(s, c, b)].headline[:3]))
                 for s, c, cond in keys if cond == a and (s, c, b) in scores]
        if pairs:
            out[f"{a}_minus_{b}"] = dict(zip(("f1_diff", "lo", "hi"), paired_difference(pairs)), pairs=len(pairs))
    return out


def per_key_table(runs: list[dict[tuple, ClipScore]]) -> dict[str, dict]:
    tot: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for scores in runs:
        for s in scores.values():
            for key, (a, b, c) in s.per_key.items():
                t = tot[key]
                t[0], t[1], t[2] = t[0] + a, t[1] + b, t[2] + c
    out = {}
    for key, (a, b, c) in sorted(tot.items()):
        p, r, f = prf(a, b, c)
        out[key] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
                    "gold_per_run": round((a + c) / len(runs), 1)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default=None, help="served extraction model label (default: HERALD_LLM_MODEL)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cards", default=str(ROOT / "eval" / "field_cards_v1.jsonl"))
    ap.add_argument("--manifest", default=str(ROOT / "eval" / "field_v1.jsonl"))
    ap.add_argument("--omissions", default=None, help="reviewed file: facts the speaker never said, per clip")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.jsonl"))
    ap.add_argument("--summary-dir", default=str(ROOT / "eval" / "dumps" / "field_v1"))
    ap.add_argument("--private-dir", default=str(AUDIO / "_bench"), help="per-clip details with transcripts")
    ap.add_argument("--cache", default=str(AUDIO / "_transcripts.jsonl"), help="speech-to-text cache")
    a = ap.parse_args(argv)

    from eval.bench_extract import build_extractor
    from herald.config import Settings
    from herald.models.stt import WhisperSTT

    protocol = yaml.safe_load((ROOT / "eval" / "field" / "protocol.yaml").read_text())
    conditions = [c["id"] for c in protocol["conditions"]]
    cards = load_cards(Path(a.cards))
    clips = load_clips(Path(a.manifest), cards)
    if not clips:
        raise SystemExit("no recordings in the manifest yet (record with eval/field/recorder.py)")
    settings = Settings.from_env()
    stt = WhisperSTT(settings.stt_model, offline=settings.models_offline)
    transcripts = transcribe(clips, stt, Path(a.cache))
    _, extractor, client = build_extractor("llm", a.model)
    model = client.model_name()
    if not client.available():
        raise SystemExit(f"extraction model {model!r} is not being served (zrt status)")
    omitted = load_omissions(Path(a.omissions) if a.omissions else None)
    private = Path(a.private_dir) / model
    private.mkdir(parents=True, exist_ok=True)
    runs, said_runs, rows = [], [], []
    for run in range(1, a.runs + 1):
        preds = extract(clips, cards, transcripts, extractor)
        scores = {clip_key(c): score_clip(cards[c["card"]].facts, preds[clip_key(c)]["pred"]) for c in clips}
        runs.append(scores)
        res = aggregate(clips, scores, conditions)
        if omitted:
            said = {clip_key(c): score_clip(cards[c["card"]].facts, preds[clip_key(c)]["pred"],
                                            omitted.get(clip_key(c), ())) for c in clips}
            said_runs.append(said)
            res["said"] = aggregate(clips, said, conditions)
        lat = sorted(p["ms"] for p in preds.values())
        row = {"extractor": f"llm:{model}", "set": "field_v1", "gold": a.cards, "stt": stt.model, "run": run,
               "clips": len(clips), "speakers": len({c["speaker"] for c in clips}), **res,
               "json_invalid": sum(p["error"] is not None for p in preds.values()),
               "latency_ms_p50": round(statistics.median(lat)), "latency_ms_p95": round(lat[int(0.95 * (len(lat) - 1))]),
               "stt_ms_p50": round(statistics.median(t["ms"] for t in transcripts.values())),
               "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        rows.append(row)
        with open(a.out, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        with open(private / f"run{run}.jsonl", "w") as fh:
            for c in clips:
                k = clip_key(c)
                fh.write(json.dumps({"speaker": k[0], "card": k[1], "condition": k[2],
                                     "transcript": transcripts[k]["text"], **preds[k], **scores[k].to_json()},
                                    default=str) + "\n")
        print(f"run {run}: F1 {row['f1']} (95% {row['ci95_clips']}, speakers {row['ci95_speakers']}) "
              f"P {row['precision']} R {row['recall']} role {row['role_acc']} · all keys {row['all_keys']['f1']} · "
              + " · ".join(f"{k} {v['f1']}" for k, v in row["by_condition"].items()))
    with open(private / "omissions_review.jsonl", "w") as fh:        # from run 1: what a reviewer checks
        for c in clips:
            k = clip_key(c)
            if runs[0][k].missed_facts:
                fh.write(json.dumps({"speaker": k[0], "card": k[1], "condition": k[2],
                                     "transcript": transcripts[k]["text"], "missed": runs[0][k].missed_facts,
                                     "omitted": []}, default=str) + "\n")
    summary = {"model": model, "stt": stt.model, "cards": a.cards, "clips": len(clips),
               "speakers": rows[0]["speakers"], "runs": len(rows),
               "f1_by_run": [r["f1"] for r in rows], "f1_spread": round(max(r["f1"] for r in rows) - min(r["f1"] for r in rows), 3),
               "run1": rows[0], "per_key_as_carded": per_key_table(runs),
               **({"per_key_said": per_key_table(said_runs)} if said_runs else {})}
    Path(a.summary_dir).mkdir(parents=True, exist_ok=True)
    (Path(a.summary_dir) / f"{model}_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(f"F1 over runs {summary['f1_by_run']} (spread {summary['f1_spread']}); per-key table and intervals in "
          f"{a.summary_dir}/{model}_summary.json; review missed facts in {private}/omissions_review.jsonl")


if __name__ == "__main__":
    main()
