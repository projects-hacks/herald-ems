#!/usr/bin/env python3
"""Field robustness benchmark (eval/field/README.md): people's own-words recordings of the fact cards, through the
product's speech-to-text (Whisper) and extractor, scored against the cards with the benchmark's atoms.

  python eval/field_bench.py --model ems-e-fp8 --runs 3
  python eval/field_bench.py --model ems-e-fp8 --runs 3 --omissions ~/herald-field-audio/omissions.jsonl

Speech-to-text runs once per clip (greedy decoding) and is cached in the shared audio folder, keyed by the audio and
a fingerprint of the Whisper model, priming prompt and adapter; the extractor runs --runs times, called exactly as
the app calls it (the card's mic, speaker and dispatch). Reported per run: headline precision/recall/F1 (the gold-v2
definition, so it sits next to the held-out numbers), F1 over every key on the cards, role accuracy, quiet vs noise,
95% intervals (clips; speakers as clusters), and the quiet-minus-noise difference resampled by speaker; per key:
precision/recall pooled over runs.

Scoring is "as carded": a fact the speaker forgot to say counts as a miss. Each run also writes a review sheet: for
every clip, its audio file, the card text and every card fact, with no model output. A reviewer listens to each
clip, moves the facts the speaker really never said into "omitted", saves the sheet under another name and passes
it back with --omissions. The "said" score is then reported beside the as-carded one, never instead of it.

Outputs: one summary line per run in --out (eval/results.jsonl); the spread over runs and the per-key table in
eval/dumps/field_v1/<model>_summary.json; per-clip details (they contain transcripts, i.e. what people said) and
the review sheet in the shared audio folder's _bench/, which is outside git like the audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from eval.field.cards import Card, load_cards  # noqa: E402
from eval.field.manifest import AUDIO_DIR, ConsentLog, Manifest, read_jsonl, write_jsonl  # noqa: E402
from eval.field.scoring import ClipScore, itemize, omission_ids, score_clip  # noqa: E402
from eval.field.stats import bootstrap_f1, cluster_bootstrap_f1, paired_difference  # noqa: E402
from eval.visionbench.common import latency, prf, sha  # noqa: E402
from herald.core.schema import source_role  # noqa: E402
from herald.core.vocabulary import Vocabulary, default_vocabulary  # noqa: E402

STT_ADAPTER = ROOT / "herald" / "models" / "stt.py"          # holds the decoding settings


def clip_key(c: dict) -> tuple[str, str, str]:
    return c["speaker"], c["card"], c["condition"]


def load_clips(manifest: Path, cards: dict[str, Card], audio_dir: Path) -> list[dict]:
    """Manifest rows with their audio. Refuses rows of a speaker who withdrew: their voice must never be scored."""
    rows = Manifest(manifest).rows()
    withdrawn = {e["speaker"] for e in ConsentLog(audio_dir).entries() if e["event"] == "withdrawn"}
    gone = sorted({r["speaker"] for r in rows} & withdrawn)
    if gone:
        raise SystemExit(f"the manifest still has clips of speakers who withdrew: {', '.join(gone)}. "
                         "Remove their lines from the manifest (the recorder does this when it runs the withdrawal).")
    clips, missing = [], []
    for row in rows:
        if row["card"] not in cards:
            raise SystemExit(f"manifest names card {row['card']}, which is not in the cards file")
        path = Path(row["file"]) if Path(row["file"]).is_absolute() else Path(audio_dir) / row["file"]
        (clips if path.exists() else missing).append({**row, "path": path})
    if missing:
        raise SystemExit(f"{len(missing)} clips in the manifest have no audio file, e.g. {missing[0]['path']}")
    return clips


def stt_fingerprint(stt) -> str:
    """The speech-to-text setup a transcript came from: model, priming prompt, and the adapter's decoding code. A
    change to any of them makes every cached transcript stale."""
    parts = {"model": stt.model, "prompt": getattr(stt, "prompt", ""),
             "adapter": sha(STT_ADAPTER) if STT_ADAPTER.exists() else None}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:12]


def transcribe(clips: list[dict], stt, cache_path: Path) -> dict[tuple, dict]:
    """(speaker, card, condition) -> {"text", "ms"}; cached by audio hash and the speech-to-text fingerprint."""
    import soundfile as sf
    cache = {r["key"]: r for r in read_jsonl(cache_path)}
    setup = stt_fingerprint(stt)
    out = {}
    for c in clips:
        key = f"{setup}:{hashlib.sha1(c['path'].read_bytes()).hexdigest()}"
        if key not in cache:
            audio, sr = sf.read(c["path"], dtype="float32")
            t0 = time.perf_counter()
            text = stt.transcribe(audio, sr)["text"]
            cache[key] = {"key": key, "speaker": c["speaker"], "stt": stt.model, "text": text,
                          "ms": round((time.perf_counter() - t0) * 1000)}
        out[clip_key(c)] = cache[key]
    write_jsonl(cache_path, list(cache.values()))
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


def review_sheet(clips: list[dict], cards: dict[str, Card]) -> list[dict]:
    """What the omission reviewer works from: the audio (listen, don't trust a transcript: a fact Whisper misheard was
    said, and that miss is what this test measures), the card, and every card fact, list items one at a time. No
    model output, so the result is the same whichever model or run is scored."""
    return [{"speaker": c["speaker"], "card": c["card"], "condition": c["condition"], "audio": str(c["path"]),
             "say": list(cards[c["card"]].say), "facts": [list(f) for f in itemize(cards[c["card"]].facts)],
             "omitted": []} for c in clips]


def load_omissions(path: Path | None, clips: list[dict], cards: dict[str, Card],
                   vocab: Vocabulary) -> tuple[dict[tuple, set[str]], list[str]]:
    """The reviewed sheet -> clip -> omitted fact ids, plus a warning for every entry that matches no clip or no card
    fact (so a typo is never silently ignored). Blank lines are fine."""
    if not path:
        return {}, []
    known = {clip_key(c): c for c in clips}
    out, warnings = {}, []
    for r in read_jsonl(Path(path)):
        k = (r.get("speaker"), r.get("card"), r.get("condition"))
        if not r.get("omitted"):
            continue
        if k not in known:
            warnings.append(f"{k}: not a clip in the manifest; its omissions are ignored")
            continue
        ids, unmatched = omission_ids(cards[k[1]].facts, r["omitted"], vocab)
        warnings += [f"{k}: omitted {e} matches no fact on card {k[1]}; ignored" for e in unmatched]
        out[k] = ids
    return out, warnings


def aggregate(clips: list[dict], scores: dict[tuple, ClipScore], conditions: list[str]) -> dict:
    """Headline and all-keys numbers with intervals, by condition, and the paired condition difference."""
    def counts(part: str, keys) -> list[tuple[int, int, int]]:
        return [tuple(getattr(scores[k], part)[:3]) for k in keys]

    keys = [clip_key(c) for c in clips]
    tp, fp, fn, role_ok = (sum(scores[k].headline[i] for k in keys) for i in range(4))
    by_speaker = defaultdict(list)
    for k in keys:
        by_speaker[k[0]].append(k)
    head = prf(tp, fp, fn)
    out = {"precision": head["precision"], "recall": head["recall"], "f1": head["f1"],
           "role_acc": round(role_ok / tp, 3) if tp else 0.0, "counts": {"tp": tp, "fp": fp, "fn": fn},
           "ci95_clips": bootstrap_f1(counts("headline", keys)),
           "ci95_speakers": cluster_bootstrap_f1({s: counts("headline", ks) for s, ks in by_speaker.items()})}
    at, af, an = (sum(scores[k].all_keys[i] for k in keys) for i in range(3))
    out["all_keys"] = {"f1": prf(at, af, an)["f1"], "ci95_clips": bootstrap_f1(counts("all_keys", keys)),
                       "ci95_speakers": cluster_bootstrap_f1({s: counts("all_keys", ks)
                                                              for s, ks in by_speaker.items()})}
    out["by_condition"] = {}
    for cond in conditions:
        ck = [k for k in keys if k[2] == cond]
        if ck:
            ct = [sum(scores[k].headline[i] for k in ck) for i in range(3)]
            out["by_condition"][cond] = {"clips": len(ck), "f1": prf(*ct)["f1"],
                                         "ci95_clips": bootstrap_f1(counts("headline", ck))}
    if len(conditions) >= 2:
        a, b = conditions[:2]
        pairs = defaultdict(list)                  # speaker -> [(first-condition counts, second-condition counts)]
        for s, c, cond in keys:
            if cond == a and (s, c, b) in scores:
                pairs[s].append((tuple(scores[(s, c, a)].headline[:3]), tuple(scores[(s, c, b)].headline[:3])))
        if pairs:
            out[f"{a}_minus_{b}"] = dict(zip(("f1_diff", "lo", "hi"), paired_difference(pairs)),
                                         pairs=sum(map(len, pairs.values())), speakers=len(pairs))
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
        m = prf(a, b, c)
        out[key] = {"precision": m["precision"], "recall": m["recall"], "f1": m["f1"],
                    "gold_per_run": round((a + c) / len(runs), 1)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default=None, help="served extraction model label (default: HERALD_LLM_MODEL)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cards", default=str(ROOT / "eval" / "field_cards_v1.jsonl"))
    ap.add_argument("--manifest", default=str(ROOT / "eval" / "field_v1.jsonl"))
    ap.add_argument("--audio-dir", default=str(AUDIO_DIR), help="the shared recordings folder")
    ap.add_argument("--omissions", default=None, help="the reviewed sheet: facts each speaker never said, per clip")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.jsonl"))
    ap.add_argument("--summary-dir", default=str(ROOT / "eval" / "dumps" / "field_v1"))
    ap.add_argument("--private-dir", default=None, help="per-clip details with transcripts (default <audio-dir>/_bench)")
    ap.add_argument("--cache", default=None, help="speech-to-text cache (default <audio-dir>/_transcripts.jsonl)")
    a = ap.parse_args(argv)
    audio_dir = Path(a.audio_dir).expanduser()
    private_root = Path(a.private_dir) if a.private_dir else audio_dir / "_bench"
    cache = Path(a.cache) if a.cache else audio_dir / "_transcripts.jsonl"

    from eval.bench_extract import build_extractor
    from herald.config import Settings
    from herald.models.stt import WhisperSTT

    protocol = yaml.safe_load((ROOT / "eval" / "field" / "protocol.yaml").read_text())
    conditions = [c["id"] for c in protocol["conditions"]]
    vocab = default_vocabulary()
    cards = load_cards(Path(a.cards), vocab)
    clips = load_clips(Path(a.manifest), cards, audio_dir)
    if not clips:
        raise SystemExit("no recordings in the manifest yet (record with python -m eval.field.recorder)")
    omitted, warnings = load_omissions(Path(a.omissions).expanduser() if a.omissions else None, clips, cards, vocab)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    settings = Settings.from_env()
    stt = WhisperSTT(settings.stt_model, offline=settings.models_offline)
    transcripts = transcribe(clips, stt, cache)
    _, extractor, client = build_extractor("llm", a.model)
    model = client.model_name()
    if not client.available():
        raise SystemExit(f"extraction model {model!r} is not being served (zrt status)")
    inputs = {"cards": sha(Path(a.cards)), "stt": stt_fingerprint(stt),
              **({"omissions": sha(Path(a.omissions).expanduser())} if a.omissions else {})}
    private = private_root / model
    private.mkdir(parents=True, exist_ok=True)
    runs, said_runs, rows = [], [], []
    for run in range(1, a.runs + 1):
        preds = extract(clips, cards, transcripts, extractor)
        scores = {clip_key(c): score_clip(cards[c["card"]].facts, preds[clip_key(c)]["pred"]) for c in clips}
        runs.append(scores)
        res = aggregate(clips, scores, conditions)
        if a.omissions:
            said = {clip_key(c): score_clip(cards[c["card"]].facts, preds[clip_key(c)]["pred"],
                                            omitted.get(clip_key(c), ())) for c in clips}
            said_runs.append(said)
            res["said"] = {**aggregate(clips, said, conditions), "clips_reviewed": len(omitted),
                           "facts_omitted": sum(map(len, omitted.values())), "warnings": len(warnings)}
        lat = latency([p["ms"] for p in preds.values()])
        row = {"extractor": f"llm:{model}", "set": "field_v1", "gold": a.cards, "stt": stt.model, "run": run,
               "clips": len(clips), "speakers": len({c["speaker"] for c in clips}), **res,
               "json_invalid": sum(p["error"] is not None for p in preds.values()),
               "latency_ms_p50": lat["latency_ms_p50"], "latency_ms_p95": lat["latency_ms_p95"],
               "stt_ms_p50": latency([t["ms"] for t in transcripts.values()])["latency_ms_p50"],
               "inputs": inputs, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        rows.append(row)
        with open(a.out, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        write_jsonl(private / f"run{run}.jsonl",
                    [{"speaker": k[0], "card": k[1], "condition": k[2], "transcript": transcripts[k]["text"],
                      **preds[k], **scores[k].to_json()} for k in map(clip_key, clips)])
        print(f"run {run}: F1 {row['f1']} (95% {row['ci95_clips']}, speakers {row['ci95_speakers']}) "
              f"P {row['precision']} R {row['recall']} role {row['role_acc']} · all keys {row['all_keys']['f1']} · "
              + " · ".join(f"{k} {v['f1']}" for k, v in row["by_condition"].items()))
    sheet = private_root / "omissions_review.jsonl"
    if a.omissions and sheet.resolve() == Path(a.omissions).expanduser().resolve():
        print(f"not rewriting {sheet}: it is the --omissions file")
    else:
        write_jsonl(sheet, review_sheet(clips, cards))
    summary = {"model": model, "stt": stt.model, "cards": a.cards, "clips": len(clips),
               "speakers": rows[0]["speakers"], "runs": len(rows), "inputs": inputs,
               "f1_by_run": [r["f1"] for r in rows], "f1_spread": round(max(r["f1"] for r in rows) - min(r["f1"] for r in rows), 3),
               "run1": rows[0], "per_key_as_carded": per_key_table(runs),
               **({"per_key_said": per_key_table(said_runs)} if said_runs else {})}
    Path(a.summary_dir).mkdir(parents=True, exist_ok=True)
    (Path(a.summary_dir) / f"{model}_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(f"F1 over runs {summary['f1_by_run']} (spread {summary['f1_spread']}); per-key table and intervals in "
          f"{a.summary_dir}/{model}_summary.json; omission review sheet (listen to each clip) in {sheet}")


if __name__ == "__main__":
    main()
