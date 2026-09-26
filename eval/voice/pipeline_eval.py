#!/usr/bin/env python3
"""Voice pipeline evaluation: does Herald hear the cabin, keep what matters clinically, and ignore the rest?

Measures the real server-side path per clip, exactly as `POST /api/audio` runs it: `WhisperSTT` (priming prompt,
the gates in config/stt.yaml) -> the production speech extractor (herald/extraction/model.py over the served
fine-tuned label the app uses) -> the vocabulary's plausibility check every fact passes on ingest -> facts. Scored
with eval/bench_extract.py's scorer v2 against the adjudicated held-out gold. No new scorer.

Three clip sets, spoken by Piper TTS (scripts/asr_tts.py; TTS is a floor, not field performance):
  clinical  the held-out gold (eval/gold_v2.jsonl, all 100 lines) plus a stratified 20 of eval/gold_es_v1.jsonl,
            each clean and under cabin noise at 10 dB and 5 dB SNR (scripts/cabin_noise.py). The same lines also
            go through the extractor as clean text, so ASR loss is separated from extraction loss.
  chatter   eval/voice/chatter.txt: non-clinical crew and family talk (clean and at 10 dB). Expected facts: none.
  noise     silence, cabin noise at several levels, a siren/beep-heavy mix, babble (3-4 chatter clips summed at low
            level). Expected facts: none.
The old speech path (the prompt with example values at 5a1549e, no gates) is run on chatter and noise for a
before/after of "Herald invented something".

Two extraction modes, both the app's: `ambient` (the continuous-listening path: someone else's mic, role unknown,
"Speaker not identified", the call's dispatch) and `bench` (the gold row's own by/speaker, as bench_extract.py
does, so the numbers compare with the published held-out results).

  PY=~/miniforge3/envs/zgx/bin/python
  $PY eval/voice/pipeline_eval.py plan
  scripts/run_job.py --name voice-tts --need-gib 4 -- $PY eval/voice/pipeline_eval.py tts
  scripts/run_job.py --name voice-eval --gpu --need-gib 8 --wait 600 -- $PY eval/voice/pipeline_eval.py run --runs 3
  $PY eval/voice/pipeline_eval.py report
Outputs go to eval/voice/out/ (gitignored). `run` resumes: a run whose files exist is not repeated.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.bench_extract import FREE_TEXT, atoms, build_coder, group_atoms, group_of, score  # noqa: E402
from herald.config import Settings  # noqa: E402
from herald.core.schema import CapturedBy, Role, source_role  # noqa: E402
from herald.core.vocabulary import default_vocabulary  # noqa: E402
from herald.extraction import ModelExtractor  # noqa: E402
from herald.models import LocalLLMClient  # noqa: E402
from scripts.asr_layer import cfg as noise_cfg, speakable  # noqa: E402
from scripts.cabin_noise import SR, cabin_noise, mix  # noqa: E402

HERE = ROOT / "eval" / "voice"
OUT = HERE / "out"
GOLD_EN, GOLD_EN_GFAST, GOLD_EN_BROAD = (ROOT / "eval" / f"gold_v2{s}.jsonl" for s in ("", "_gfast", "_broad"))
GOLD_ES = ROOT / "eval" / "gold_es_v1.jsonl"
ES_VOICES = ("es_MX-claude-high", "es_MX-ald-medium")
CONDITIONS = {"clean": None, "snr10": 10, "snr5": 5}
CHATTER_CONDITIONS = {"clean": None, "snr10": 10}
# config/prompts/stt_prompt.txt as it was at main 5a1549e (`git show 5a1549e:config/prompts/stt_prompt.txt`): the
# example values it carried were echoed on silent clips and reached the record as a blood pressure nobody said.
OLD_PROMPT = ("Paramedic report. BP 182 over 104, pulse 92, SpO2 95 on room air, glucose 142, last known well 1:40, "
              "left facial droop, arm drift, warfarin, Eliquis, Xarelto, RACE, NEWS2.")
AMBIENT_SPEAKER = "Speaker not identified"           # herald/api/capture.py AMBIENT_SPEAKER
FAMILIES = {"vitals": ("vitals.",), "meds given": ("meds.given",), "history": ("meds.list", "meds.anticoagulant",
            "code_status", "allergies"), "deficits & exam": ("stroke.", "exam."), "patient": ("patient.",),
            "transport": ("transport.",), "trauma & ecg": ("trauma.", "ecg.", "procedures.")}


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def write_jl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")


# ---------------------------------------------------------------- plan
def stratified(rows: list[dict], n: int, rng: random.Random) -> list[dict]:
    """Rarest keys first, one line per key until every key is covered, then a random fill (scripts/asr_layer.py plan)."""
    rows = list(rows)
    rng.shuffle(rows)
    by_key: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        for k in {f[0] for f in r["facts"]}:
            by_key[k].append(i)
    picked, seen = [], set()
    for k in sorted(by_key, key=lambda k: len(by_key[k])):
        if len(picked) >= n or any(i in seen for i in by_key[k]):      # the key is already covered
            continue
        seen.add(by_key[k][0])
        picked.append(by_key[k][0])
    for i in range(len(rows)):
        if len(picked) >= n:
            break
        if i not in seen:
            seen.add(i)
            picked.append(i)
    return [rows[i] for i in picked[:n]]


def plan(a) -> None:
    c = noise_cfg()
    rng = random.Random(a.seed)
    gfast = {d["id"]: d["gfast"] for d in jl(GOLD_EN_GFAST)} if GOLD_EN_GFAST.exists() else {}
    broad = {d["id"]: d["facts"] for d in jl(GOLD_EN_BROAD)} if GOLD_EN_BROAD.exists() else {}
    lines, tts_en, tts_es, rows = [], [], [], []
    for r in jl(GOLD_EN):
        lines.append({"line": f"en_{r['id']}", "set": "clinical", "lang": "en", "source_id": r["id"], "text": r["text"],
                      "by": r.get("by", "medic"), "speaker": r.get("speaker"), "dispatch": r.get("dispatch"),
                      "facts": r["facts"], "gfast": gfast.get(r["id"], []),
                      "broad": [f for f in broad.get(r["id"], []) if group_of(f[0]) == "broad"],
                      "voice": rng.choice(c["voices"]), "length_scale": round(rng.uniform(*c["length_scale"]), 3)})
    for r in stratified(jl(GOLD_ES), a.es, random.Random(a.seed + 1)):
        lines.append({"line": f"es_{r['id']}", "set": "clinical", "lang": "es", "source_id": r["id"], "text": r["text"],
                      "by": r.get("by", "medic"), "speaker": r.get("speaker"), "dispatch": r.get("dispatch"),
                      "facts": r["facts"], "gfast": [f for f in r["facts"] if group_of(f[0]) == "gfast"],
                      "broad": [f for f in r["facts"] if group_of(f[0]) == "broad"],
                      "voice": rng.choice(ES_VOICES), "length_scale": round(rng.uniform(*c["length_scale"]), 3)})
    chatter = [t.strip() for t in (HERE / "chatter.txt").read_text(encoding="utf-8").splitlines()
               if t.strip() and not t.startswith("#")]
    for i, text in enumerate(chatter):
        lines.append({"line": f"ch_{i:03d}", "set": "chatter", "lang": "en", "source_id": f"chatter_{i:03d}", "text": text,
                      "by": "other", "speaker": None, "dispatch": None, "facts": [], "gfast": [], "broad": [],
                      "voice": rng.choice(c["voices"]), "length_scale": round(rng.uniform(*c["length_scale"]), 3)})
    for ln in lines:
        (tts_es if ln["lang"] == "es" else tts_en).append(
            {"clip": ln["line"], "said": speakable(ln["text"]), "voice": ln["voice"], "length_scale": ln["length_scale"]})
        conds = CONDITIONS if ln["set"] == "clinical" else CHATTER_CONDITIONS
        for cond, snr in conds.items():
            rows.append({**ln, "clip": f"{ln['line']}__{cond}", "condition": cond, "snr_db": snr, "wav": ln["line"],
                         "seed": rng.randrange(1 << 30)})
    noise = [("silence", {})]
    noise += [(f"cabin_{db}dBFS_s{s}", {"dbfs": db, "seed": s}) for s in (1, 2) for db in (-46, -34, -22)]
    noise += [(f"siren_beeps_{db}dBFS", {"dbfs": db, "seed": 9, "siren": 1, "beeps": 1}) for db in (-30, -20)]
    ch_lines = [ln["line"] for ln in lines if ln["set"] == "chatter"]
    for s in (1, 2, 3):
        pick = random.Random(100 + s).sample(ch_lines, 4)
        noise.append((f"babble_s{s}", {"dbfs": -30, "seed": s, "voices": pick}))
    noise.append(("babble_over_cabin", {"dbfs": -30, "seed": 4, "voices": random.Random(104).sample(ch_lines, 3),
                                        "cabin_dbfs": -34}))
    for name, spec in noise:
        rows.append({"clip": f"n_{name}", "set": "noise", "lang": None, "source_id": name, "text": "", "by": "other",
                     "speaker": None, "dispatch": None, "facts": [], "gfast": [], "broad": [], "condition": name,
                     "snr_db": None, "wav": None, "noise": spec, "seed": spec.get("seed", 0)})
    write_jl(OUT / "plan.jsonl", rows)
    write_jl(OUT / "tts_en.jsonl", tts_en)
    write_jl(OUT / "tts_es.jsonl", tts_es)
    keys = Counter(f[0] for ln in lines if ln["set"] == "clinical" for f in ln["facts"])
    print(json.dumps({"clips": len(rows), "lines": len(lines), "clinical_en": sum(ln["lang"] == "en" and ln["set"] == "clinical" for ln in lines),
                      "clinical_es": sum(ln["lang"] == "es" for ln in lines), "chatter": len(chatter),
                      "noise": len(noise), "clinical_keys": len(keys), "tts_en": len(tts_en), "tts_es": len(tts_es)}))


# ---------------------------------------------------------------- tts
def tts(a) -> None:
    """Piper in its own venvs (never the zgx env): scripts/asr_tts.py for English, the same script under the Spanish
    venv for the es_MX voices. Existing wavs are kept."""
    wav = OUT / "wav"
    for plan_file, py, voices in ((OUT / "tts_en.jsonl", a.piper_en, a.voices_en), (OUT / "tts_es.jsonl", a.piper_es, a.voices_es)):
        if not plan_file.exists() or not jl(plan_file):
            continue
        cmd = [py, str(ROOT / "scripts" / "asr_tts.py"), "--plan", str(plan_file), "--voices", voices, "--out", str(wav),
               "--workers", str(a.workers)]
        print(" ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, cwd=ROOT)
    print(json.dumps({"wavs": len(list(wav.glob("*.wav")))}))


# ---------------------------------------------------------------- audio
def rms_to(x, dbfs: float):
    import numpy as np
    r = float(np.sqrt(np.mean(x ** 2)))
    return (x / r * 10 ** (dbfs / 20)).astype(np.float32) if r > 0 else x.astype(np.float32)


def load_wav(name: str):
    import soundfile as sf
    from herald.models.stt import WhisperSTT
    audio, sr = sf.read(OUT / "wav" / f"{name}.wav", dtype="float32")
    return WhisperSTT._mono16k(audio, sr)


def clip_audio(row: dict, c: dict):
    """The clip's samples at 16 kHz, reproducible from the plan (seeded noise, the shared TTS wav)."""
    import numpy as np
    if row["set"] != "noise":
        return mix(load_wav(row["wav"]), row["snr_db"], np.random.default_rng(row["seed"]), c, SR)[0].astype(np.float32)
    spec, n = row["noise"], 8 * SR
    if row["source_id"] == "silence":
        return np.zeros(n, np.float32)
    rng = np.random.default_rng(1000 + spec["seed"])
    if "voices" in spec:
        out = np.zeros(n, np.float32)
        for name in spec["voices"]:
            v = load_wav(name)[:n]
            start = int(rng.integers(0, max(1, n - len(v) // 2)))
            take = min(len(v), n - start)
            out[start:start + take] += v[:take]
        out = rms_to(out, spec["dbfs"])
        if "cabin_dbfs" in spec:
            out = out + rms_to(cabin_noise(n, rng, {**c, "siren_share": 0, "beep_share": 0})[0], spec["cabin_dbfs"])
        return out.astype(np.float32)
    noise, _ = cabin_noise(n, rng, {**c, "siren_share": spec.get("siren", 0), "beep_share": spec.get("beeps", 0)})
    return rms_to(noise, spec["dbfs"])


# ---------------------------------------------------------------- run
class Extractors:
    """One client and extractor per worker thread (ModelExtractor keeps per-call state), the drug coder shared under a
    lock: the same wiring as herald/api/context.py and eval/bench_extract.py, at low concurrency on the shared server."""

    def __init__(self, model: str, coder):
        self.settings = Settings.from_env()
        self.model, self.coder = model, coder
        self.local = threading.local()
        self.vocab = default_vocabulary()

    def get(self) -> ModelExtractor:
        if not hasattr(self.local, "ext"):
            client = LocalLLMClient(self.settings.llm_url, self.model)
            self.local.ext = ModelExtractor(client, vocabulary=self.vocab, finetuned_labels=self.settings.finetuned_models,
                                            coder=self.coder)
        return self.local.ext

    def extract(self, job: dict) -> dict:
        ext = self.get()
        row = job["row"]
        if job["mode"] == "ambient":          # herald/api/routes/capture.py + capture.py, ambient=true
            by, role, speaker = CapturedBy.other, Role.unknown, AMBIENT_SPEAKER
        else:                                 # eval/bench_extract.py predict(): the gold row's own source
            by = CapturedBy(row.get("by") or "medic")
            speaker = row.get("speaker")
            role = source_role(by, speaker)
        ext.last_usage = {}
        t0 = time.perf_counter()
        err, pred, rejected = None, [], []
        try:
            facts = ext.extract(job["text"], by, role, speaker, dispatch=row.get("dispatch"))
            for f in facts:                   # the plausibility check every fact meets on ingest (Incident.validate)
                try:
                    self.vocab.validate(f.key, f.value)
                    pred.append([f.key, f.value, f.role.value])
                except ValueError as e:
                    rejected.append([f.key, f.value, str(e)[:80]])
        except Exception as e:                # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:160]}"
        return {**{k: job[k] for k in ("clip", "set", "condition", "path", "mode", "lang", "source_id")}, "text": job["text"],
                "pred": pred, "rejected": rejected, "error": err, "ms": round((time.perf_counter() - t0) * 1000),
                "tokens": (ext.last_usage or {}).get("completion_tokens")}


class LockedCoder:
    def __init__(self, coder):
        self.coder, self.lock = coder, threading.Lock()
        self.release = getattr(coder, "release", None)

    def code(self, facts):
        with self.lock:
            return self.coder.code(facts)


def run(a) -> None:
    import torch
    from herald.models.stt import WhisperSTT
    rows = jl(OUT / "plan.jsonl")
    if a.smoke:                               # a few clips of every kind, into smoke_run<N>/: checks the path end to end
        keep = [r for r in rows if r["set"] == "clinical" and r["lang"] == "en"][:6]
        keep += [r for r in rows if r["set"] == "clinical" and r["lang"] == "es"][:3]
        keep += [r for r in rows if r["set"] == "chatter"][:4] + [r for r in rows if r["set"] == "noise"][:4]
        keep += [r for r in rows if r["source_id"].startswith("babble")][:1]
        rows = keep
    c = noise_cfg()
    t0 = time.perf_counter()
    audio = {r["clip"]: clip_audio(r, c) for r in rows}
    print(json.dumps({"clips": len(rows), "audio_s": round(sum(len(x) for x in audio.values()) / SR),
                      "build_s": round(time.perf_counter() - t0, 1)}), flush=True)
    settings = Settings.from_env()
    coder = build_coder(a.terminology == "on")
    xs = Extractors(a.model, LockedCoder(coder) if coder else None)
    check = LocalLLMClient(settings.llm_url, a.model)
    if not check.available():
        sys.exit(f"{a.model} is not served at {settings.llm_url} (zrt status)")
    stt = WhisperSTT(settings.stt_model, offline=settings.models_offline)
    stt.warm()
    old_rows = [r for r in rows if r["set"] in ("chatter", "noise")]
    prefix = "smoke_run" if a.smoke else "run"
    for run_id in range(1, a.runs + 1):
        rd = OUT / f"{prefix}{run_id}"
        rd.mkdir(parents=True, exist_ok=True)
        timing = {}
        stt_path = rd / "stt.jsonl"
        if run_id > a.stt_runs and (OUT / f"{prefix}{a.stt_runs}" / "stt.jsonl").exists():
            stt_rows = jl(OUT / f"{prefix}{a.stt_runs}" / "stt.jsonl")      # transcripts reused from the last STT run
            timing["stt_reused_from"] = a.stt_runs
        elif stt_path.exists():
            stt_rows = jl(stt_path)
        else:
            t1 = time.perf_counter()
            new = stt.transcribe_many([audio[r["clip"]] for r in rows], SR, batch_size=a.batch)
            torch.cuda.synchronize()
            timing["stt_new_s"] = round(time.perf_counter() - t1, 1)
            saved, stt.prompt = stt.prompt, OLD_PROMPT
            try:
                t1 = time.perf_counter()
                old = stt.transcribe_many([audio[r["clip"]] for r in old_rows], SR, batch_size=a.batch, gate=False)
                torch.cuda.synchronize()
                timing["stt_old_s"] = round(time.perf_counter() - t1, 1)
            finally:
                stt.prompt = saved
            stt_rows = [{"clip": r["clip"], "path": "new", **o} for r, o in zip(rows, new)]
            stt_rows += [{"clip": r["clip"], "path": "old", **o} for r, o in zip(old_rows, old)]
            write_jl(stt_path, stt_rows)
        by_clip = {r["clip"]: r for r in rows}
        for mode in a.modes.split(","):
            fpath = rd / f"facts_{mode}.jsonl"
            if fpath.exists():
                continue
            jobs = [{"row": by_clip[s["clip"]], "clip": s["clip"], "set": by_clip[s["clip"]]["set"],
                     "condition": by_clip[s["clip"]]["condition"], "path": s["path"], "mode": mode,
                     "lang": by_clip[s["clip"]]["lang"], "source_id": by_clip[s["clip"]]["source_id"], "text": s["text"]}
                    for s in stt_rows if s["text"]]
            seen_lines = set()
            for r in rows:                    # the same lines as clean text: extraction loss without ASR
                if r["set"] == "clinical" and r["line"] not in seen_lines:
                    seen_lines.add(r["line"])
                    jobs.append({"row": r, "clip": r["line"] + "__text", "set": "clinical", "condition": "text", "path": "text",
                                 "mode": mode, "lang": r["lang"], "source_id": r["source_id"], "text": r["text"]})
            t1 = time.perf_counter()
            with ThreadPoolExecutor(a.concurrency) as ex:
                results = list(ex.map(xs.extract, jobs))
            timing[f"extract_{mode}_s"] = round(time.perf_counter() - t1, 1)
            timing[f"extract_{mode}_calls"] = len(jobs)
            write_jl(fpath, results)
        (rd / "timing.json").write_text(json.dumps({**timing, "model": a.model, "stt_model": settings.stt_model,
                                                    "terminology": coder.release if coder else None,
                                                    "concurrency": a.concurrency}, indent=1))
        print(json.dumps({"run": run_id, **timing}), flush=True)


# ---------------------------------------------------------------- report
def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def fam(key: str) -> str:
    for name, prefixes in FAMILIES.items():
        if any(key == p or key.startswith(p) for p in prefixes):
            return name
    return "other"


def clinical_scores(rows_by_clip: dict, facts: list[dict], stt_by_clip: dict, lang: str | None, condition: str) -> dict:
    """bench_extract's scoring over the clinical clips of one condition: structured keys (headline), free text,
    the gfast and broad groups, plus per-family counts. A clip the gates dropped, or with no text, scores its gold as
    missed (that is what the record would show)."""
    preds = {f["clip"]: f for f in facts if f["set"] == "clinical" and f["condition"] == condition}
    S = Counter()
    fams: dict[str, Counter] = defaultdict(Counter)
    extra, dropped, dropped_clips = [], Counter(), []
    n = 0
    for clip, r in rows_by_clip.items():
        if r["set"] != "clinical" or (lang and r["lang"] != lang):
            continue
        if condition == "text":               # the clean-text control: one per line, keyed <line>__text
            if r["condition"] != "clean":
                continue
            clip = r["line"] + "__text"
        elif r["condition"] != condition:
            continue
        n += 1
        f = preds.get(clip)
        pred = [tuple(x) for x in (f["pred"] if f else [])]
        if condition != "text":
            s = stt_by_clip.get((clip, "new"), {})
            if s.get("dropped"):
                dropped[s["dropped"]] += 1
                dropped_clips.append({"clip": clip, "reason": s["dropped"], "language": s.get("language"),
                                      "read_prob": (s.get("signals") or {}).get("read_language_prob"),
                                      "text": r["text"][:90]})
        tp, fp, fn, role_ok, ex, _ = score(r["facts"], pred)
        S.update({"tp": tp, "fp": fp, "fn": fn, "role_ok": role_ok, "rejected": len(f["rejected"]) if f else 0,
                  "errors": 1 if f and f["error"] else 0})
        extra += [[clip] + list(x) for x in ex]
        ft = score(r["facts"], pred, free_text=True)
        S.update({"ft_tp": ft[0], "ft_fp": ft[1], "ft_fn": ft[2]})
        for grp, gold_g in (("gfast", r["gfast"]), ("broad", r["broad"])):
            g = group_atoms([tuple(x[:3]) for x in gold_g])
            p = group_atoms([x for x in pred if group_of(x[0]) == grp])
            S.update({f"{grp}_tp": len(set(g) & set(p)), f"{grp}_fp": len(set(p) - set(g)), f"{grp}_fn": len(set(g) - set(p))})
        g_all, p_all = atoms([tuple(x[:3]) for x in r["facts"] if x[0] not in FREE_TEXT]), atoms([x for x in pred if x[0] not in FREE_TEXT])
        for k in set(g_all) | set(p_all):
            fams[fam(k[0])].update({"tp": k in g_all and k in p_all, "fp": k in p_all and k not in g_all,
                                    "fn": k in g_all and k not in p_all})
    p, r_, f1 = prf(S["tp"], S["fp"], S["fn"])
    out = {"n": n, "dropped": dict(dropped), "tp": S["tp"], "fp": S["fp"], "fn": S["fn"], "precision": round(p, 3),
           "recall": round(r_, 3), "f1": round(f1, 3), "role_acc": round(S["role_ok"] / S["tp"], 3) if S["tp"] else None,
           "free_text_f1": round(prf(S["ft_tp"], S["ft_fp"], S["ft_fn"])[2], 3),
           "gfast_f1": round(prf(S["gfast_tp"], S["gfast_fp"], S["gfast_fn"])[2], 3),
           "broad_f1": round(prf(S["broad_tp"], S["broad_fp"], S["broad_fn"])[2], 3),
           "rejected_implausible": S["rejected"], "errors": S["errors"],
           "families": {k: {"recall": round(v["tp"] / (v["tp"] + v["fn"]), 3) if v["tp"] + v["fn"] else None,
                            "precision": round(v["tp"] / (v["tp"] + v["fp"]), 3) if v["tp"] + v["fp"] else None,
                            "gold": v["tp"] + v["fn"]} for k, v in sorted(fams.items())},
           "extra": extra, "dropped_clips": dropped_clips}
    return out


def false_facts(rows_by_clip: dict, facts: list[dict], stt_by_clip: dict, set_name: str, path: str) -> dict:
    clips = [c for c, r in rows_by_clip.items() if r["set"] == set_name]
    dropped, texts, with_facts, n_facts, rejected, items = Counter(), 0, 0, 0, 0, []
    preds = {f["clip"]: f for f in facts if f["set"] == set_name and f["path"] == path}
    for clip in clips:
        s = stt_by_clip.get((clip, path))
        if s is None:
            continue
        if s.get("dropped"):
            dropped[s["dropped"]] += 1
        if s["text"]:
            texts += 1
        f = preds.get(clip)
        if f:
            rejected += len(f["rejected"])
            if f["pred"]:
                with_facts += 1
                n_facts += len(f["pred"])
                items.append({"clip": clip, "transcript": f["text"], "facts": f["pred"], "rejected": f["rejected"]})
    return {"clips": len(clips), "dropped": dict(dropped), "with_text": texts, "clips_with_facts": with_facts,
            "false_facts": n_facts, "rejected_implausible": rejected, "items": items}


def agg(values: list) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "-"
    if len(vals) == 1:
        return f"{vals[0]:.3f}" if isinstance(vals[0], float) else str(vals[0])
    m = statistics.mean(vals)
    return (f"{m:.3f} [{min(vals):.3f}-{max(vals):.3f}]" if isinstance(vals[0], float)
            else f"{m:.1f} [{min(vals)}-{max(vals)}]")


def report(a) -> None:
    rows = jl(OUT / "plan.jsonl")
    rows_by_clip = {r["clip"]: r for r in rows}
    runs = sorted(p for p in OUT.glob("run*") if (p / "timing.json").exists())
    modes = a.modes.split(",")
    per_run = []
    for rd in runs:
        stt_rows = jl(rd / "stt.jsonl") if (rd / "stt.jsonl").exists() else jl(OUT / "run1" / "stt.jsonl")
        stt_by_clip = {(s["clip"], s["path"]): s for s in stt_rows}
        res = {"run": rd.name, "timing": json.loads((rd / "timing.json").read_text()), "modes": {}}
        for mode in modes:
            if not (rd / f"facts_{mode}.jsonl").exists():
                continue
            facts = jl(rd / f"facts_{mode}.jsonl")
            m = {"clinical": {}, "chatter": {}, "noise": {}}
            for lang in ("en", "es", None):
                for cond in ("text", "clean", "snr10", "snr5"):
                    m["clinical"][f"{lang or 'all'}/{cond}"] = clinical_scores(rows_by_clip, facts, stt_by_clip, lang, cond)
            for set_name in ("chatter", "noise"):
                for path in ("new", "old"):
                    m[set_name][path] = false_facts(rows_by_clip, facts, stt_by_clip, set_name, path)
            res["modes"][mode] = m
        per_run.append(res)
    (OUT / "report.json").write_text(json.dumps(per_run, indent=1, ensure_ascii=False, default=str))

    lines = [f"# Voice pipeline evaluation ({len(per_run)} runs)", ""]
    t = per_run[0]["timing"] if per_run else {}
    lines += [f"Model `{t.get('model')}` via the app's extractor; STT `{t.get('stt_model')}`; drug coding "
              f"`{t.get('terminology')}`; extraction concurrency {t.get('concurrency')}. Clips: "
              f"{sum(r['set'] == 'clinical' for r in rows)} clinical ({sum(r['set'] == 'clinical' and r['lang'] == 'en' for r in rows)} en, "
              f"{sum(r['set'] == 'clinical' and r['lang'] == 'es' for r in rows)} es), {sum(r['set'] == 'chatter' for r in rows)} chatter, "
              f"{sum(r['set'] == 'noise' for r in rows)} noise-only. TTS speech (Piper), synthetic cabin noise: a floor, not field performance.", ""]
    for mode in modes:
        runs_m = [pr["modes"][mode] for pr in per_run if mode in pr["modes"]]
        if not runs_m:
            continue
        lines += [f"## Mode `{mode}`", "", "### Clinical (held-out gold spoken by TTS; bench scorer v2)", "",
                  "| lines | condition | n | dropped by gate | precision | recall | F1 | ΔF1 vs text | free-text F1 | gfast F1 | broad F1 | implausible rejected |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for lang in ("en", "es", "all"):
            base = [m["clinical"][f"{lang}/text"]["f1"] for m in runs_m]
            for cond in ("text", "clean", "snr10", "snr5"):
                cs = [m["clinical"][f"{lang}/{cond}"] for m in runs_m]
                d = Counter()
                for x in cs:
                    d.update(x["dropped"])
                dropped = ", ".join(f"{k} {v / len(cs):.1f}" for k, v in d.items()) or "0"
                delta = agg([c["f1"] - b for c, b in zip(cs, base)]) if cond != "text" else "-"
                lines.append(f"| {lang} | {cond} | {cs[0]['n']} | {dropped} | {agg([c['precision'] for c in cs])} | "
                             f"{agg([c['recall'] for c in cs])} | {agg([c['f1'] for c in cs])} | {delta} | "
                             f"{agg([c['free_text_f1'] for c in cs])} | {agg([c['gfast_f1'] for c in cs])} | "
                             f"{agg([c['broad_f1'] for c in cs])} | {agg([c['rejected_implausible'] for c in cs])} |")
        dropped_seen: dict[str, dict] = {}
        for m in runs_m:
            for cond in ("clean", "snr10", "snr5"):
                for d in m["clinical"][f"all/{cond}"]["dropped_clips"]:
                    dropped_seen.setdefault(d["clip"], d)
        if dropped_seen:
            lines += ["", "Clinical clips a gate dropped (their gold scores as missed above):", ""]
            for d in sorted(dropped_seen.values(), key=lambda d: d["clip"]):
                lines.append(f"- `{d['clip']}`: {d['reason']} (heard as {d['language']}, mass on en+es "
                             f"{d['read_prob']}) <- “{d['text']}…”")
        lines += ["", "### Recall by fact family (English; what the claim names)", "",
                  "| family | gold atoms | text | clean | snr10 | snr5 |", "|---|---|---|---|---|---|"]
        fams = sorted({k for m in runs_m for k in m["clinical"]["en/text"]["families"]})
        for f in fams:
            cells = []
            for cond in ("text", "clean", "snr10", "snr5"):
                cells.append(agg([m["clinical"][f"en/{cond}"]["families"].get(f, {}).get("recall") for m in runs_m]))
            gold = runs_m[0]["clinical"]["en/text"]["families"].get(f, {}).get("gold", 0)
            lines.append(f"| {f} | {gold} | " + " | ".join(cells) + " |")
        lines += ["", "### Chatter and noise (expected facts: none)", "",
                  "| set | speech path | clips | dropped: no speech / language / loop | clips with text | clips with a fact | false facts | implausible rejected |",
                  "|---|---|---|---|---|---|---|---|"]
        for set_name in ("chatter", "noise"):
            for path, label in (("new", "new (vocabulary prompt + gates)"), ("old", "old (values in prompt, no gates)")):
                cs = [m[set_name][path] for m in runs_m]
                dr = lambda k: agg([c["dropped"].get(k, 0) for c in cs])  # noqa: E731
                lines.append(f"| {set_name} | {label} | {cs[0]['clips']} | {dr('no speech')} / {dr('language')} / {dr('repetition loop')} | "
                             f"{agg([c['with_text'] for c in cs])} | {agg([c['clips_with_facts'] for c in cs])} | "
                             f"{agg([c['false_facts'] for c in cs])} | {agg([c['rejected_implausible'] for c in cs])} |")
        lines += ["", "### Every false fact (chatter and noise), with its transcript", ""]
        for set_name in ("chatter", "noise"):
            for path in ("new", "old"):
                seen: dict[tuple, list] = defaultdict(list)
                for pr in per_run:
                    if mode not in pr["modes"]:
                        continue
                    for it in pr["modes"][mode][set_name][path]["items"]:
                        for f in it["facts"]:
                            seen[(it["clip"], it["transcript"], json.dumps(f, ensure_ascii=False))].append(pr["run"])
                if seen:
                    lines.append(f"**{set_name}, {path} path:**")
                    for (clip, text, f), in_runs in sorted(seen.items()):
                        lines.append(f"- `{clip}` ({', '.join(in_runs)}): {f} <- “{text[:160]}”")
                    lines.append("")
        lines += ["### Extra atoms on clinical clips, not in gold (English, snr5; by key, summed over runs)", ""]
        cnt = Counter()
        for m in runs_m:
            for x in m["clinical"]["en/snr5"]["extra"]:
                cnt[x[1]] += 1
        lines.append(", ".join(f"{k} ×{v}" for k, v in cnt.most_common(12)) or "none")
        lines.append("")
    stt1 = OUT / "run1" / "stt.jsonl"
    if stt1.exists():
        by = {(s["clip"], s["path"]): s for s in jl(stt1)}
        lines += ["## What the speech paths heard on the noise-only clips (run 1)", "",
                  "| clip | new path (vocabulary prompt + gates) | old path (values in prompt, no gates) |", "|---|---|---|"]
        for r in rows:
            if r["set"] != "noise":
                continue
            new, old = by.get((r["clip"], "new"), {}), by.get((r["clip"], "old"), {})
            cell = lambda s: (f"dropped: {s['dropped']}" if s.get("dropped") else (s.get("text") or "(no text)"))[:90].replace("|", "/")  # noqa: E731
            lines.append(f"| {r['clip']} | {cell(new)} | {cell(old)} |")
        lines.append("")
    lines += ["## Runtime", ""] + [f"- {pr['run']}: {json.dumps(pr['timing'])}" for pr in per_run] + [""]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", choices=["v2", "v3"], default="v2",
                    help="the English held-out set: v2 (the bench headline) or v3 (every call type, incl. meds given); "
                         "v3 writes to out_v3/")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--es", type=int, default=20, help="Spanish gold lines (stratified by key)")
    t = sub.add_parser("tts")
    t.add_argument("--piper-en", default=str(Path.home() / ".venvs/piper/bin/python"))
    t.add_argument("--piper-es", default=str(Path.home() / ".venvs/piper-es/bin/python"))
    t.add_argument("--voices-en", default=str(Path.home() / ".cache/piper-voices"))
    t.add_argument("--voices-es", default=str(Path.home() / ".venvs/piper-es/voices"))
    t.add_argument("--workers", type=int, default=3)
    r = sub.add_parser("run")
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--stt-runs", type=int, default=1, help="transcribe this many runs; later runs reuse the last (greedy decoding, same batches)")
    r.add_argument("--model", default="ems-e-v2-fp8", help="the served extraction label the app uses (HERALD_LLM_MODEL)")
    r.add_argument("--modes", default="ambient,bench")
    r.add_argument("--concurrency", type=int, default=3, help="requests in flight on the shared model server")
    r.add_argument("--batch", type=int, default=8)
    r.add_argument("--terminology", choices=["on", "off"], default="on", help="drug coding, as the app wires it")
    r.add_argument("--smoke", action="store_true", help="18 clips of every kind into out/smoke_run<N>/ (an end-to-end check)")
    rp = sub.add_parser("report")
    rp.add_argument("--modes", default="ambient,bench")
    a = ap.parse_args()
    global OUT, GOLD_EN, GOLD_EN_GFAST, GOLD_EN_BROAD
    if a.gold != "v2":
        OUT = HERE / f"out_{a.gold}"
        GOLD_EN, GOLD_EN_GFAST, GOLD_EN_BROAD = (ROOT / "eval" / f"gold_{a.gold}{s}.jsonl" for s in ("", "_gfast", "_broad"))
    {"plan": plan, "tts": tts, "run": run, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
