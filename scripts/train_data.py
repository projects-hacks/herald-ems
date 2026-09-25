"""Training-set helpers for scripts/build_train_set.py: decontamination against held-out text, reviewed drug-name
relabels, label overlays, and the neutral chat record. Training-data preparation only; nothing here runs in the
product (MODEL_PLAN §0k)."""
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

import yaml

RUN = 8                                   # words in a shared run that make two texts overlap


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def word_runs(text: str, n: int = RUN) -> set:
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def held_out_texts(path: str | Path) -> list[str]:
    """Every utterance text in a held-out file: JSONL lines with "text" (gold sets, adversarial benches; lines
    without a text, such as label-only overlays, are skipped) or with a "say" list (field cards), and scenario
    scripts (JSON with steps[].say)."""
    p = Path(path)
    if p.suffix == ".json":
        doc = json.loads(p.read_text())
        return [s["say"] for s in doc.get("steps", []) if isinstance(s.get("say"), str)]
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if isinstance(d.get("text"), str):
            out.append(d["text"])
        say = d.get("say")
        if isinstance(say, list):
            out += [s for s in say if isinstance(s, str)]
            out.append(" ".join(s for s in say if isinstance(s, str)))
        elif isinstance(say, str):
            out.append(say)
    return out


def expand(spec: str) -> list[str]:
    """Comma-separated paths or glob patterns -> sorted file list (a pattern that matches nothing is an error)."""
    files: list[str] = []
    for part in filter(None, (s.strip() for s in spec.split(","))):
        hits = sorted(glob.glob(part)) if any(c in part for c in "*?[") else [part]
        if not hits:
            raise FileNotFoundError(f"--decontaminate: nothing matches {part}")
        files += hits
    return files


class Decontaminator:
    """A training text overlaps the held-out texts when it shares an 8-word run with any of them, or when its words
    equal a held-out text's words (short items, such as adversarial one-liners, have no 8-word run)."""

    def __init__(self, texts: Iterable[str]):
        self.runs: set = set()
        self.whole: set = set()
        for t in texts:
            self.runs |= word_runs(t)
            w = tuple(words(t))
            if w:
                self.whole.add(w)

    @classmethod
    def from_files(cls, files: Iterable[str]) -> "Decontaminator":
        return cls(t for f in files for t in held_out_texts(f))

    def overlaps(self, text: str) -> bool:
        return bool(word_runs(text) & self.runs) or tuple(words(text)) in self.whole


class DrugRelabel:
    """A reviewed list of drug-label renames (data/annotated/drug_relabel_*.yaml): old spelling -> the name the RxNorm
    coder writes back for an exact match (LABELING_GUIDE §5c.2). Applied to list items, plain values and one record
    field, per the entry's key."""

    def __init__(self, entries: list[dict]):
        self.map: dict[tuple, str] = {}
        for e in entries:
            self.map[(e["key"], e.get("field"), e["before"])] = e["after"]
        self.applied: Counter = Counter()

    @classmethod
    def load(cls, path: Optional[str]) -> "DrugRelabel":
        return cls(yaml.safe_load(Path(path).read_text())["relabel"] if path else [])

    def _one(self, key: str, field: Optional[str], value):
        new = self.map.get((key, field, value)) if isinstance(value, str) else None
        if new is None:
            return value
        self.applied[f"{key}{'.' + field if field else ''}: {value} -> {new}"] += 1
        return new

    def fact(self, fact: list) -> list:
        k, v = fact[0], fact[1]
        if isinstance(v, list):
            v = [self._one(k, None, x) for x in v]
        elif isinstance(v, dict):
            v = {f: self._one(k, f, x) for f, x in v.items()}
        else:
            v = self._one(k, None, v)
        return [k, v, *fact[2:]]


def merge_overlay(facts: list, extra: list) -> list:
    """Add overlay facts to a line's facts. An overlay fact the line already has (same key and value) is skipped;
    repeats inside the overlay are kept (identical doses said twice become one record with a count later). An
    overlay record that extends one of the line's records (same key, every existing field equal, new fields added,
    such as before_arrival) replaces it in place, so one event never becomes two."""
    out = [list(f) for f in facts]
    original = {i: json.dumps(f[1], sort_keys=True) for i, f in enumerate(out)}
    replaced: set = set()
    for x in extra:
        same = json.dumps(x[1], sort_keys=True)
        if any(out[i][0] == x[0] and v == same for i, v in original.items()):
            continue
        if isinstance(x[1], dict):
            i = next((i for i in original if i not in replaced and out[i][0] == x[0] and isinstance(out[i][1], dict)
                      and all(x[1].get(a) == b for a, b in out[i][1].items())), None)
            if i is not None:
                out[i] = [x[0], x[1], *out[i][2:]]
                replaced.add(i)
                continue
        out.append(list(x))
    return out


def chat_messages(system: str, user: str, assistant: str) -> list[dict]:
    """The neutral chat form of one training example (system, user, assistant; plain-string contents), which any
    chat or VLM trainer can map onto its own template. The strings are exactly what the served extractor sends and
    parses (herald/extraction/profiles.py builds the user text)."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user},
            {"role": "assistant", "content": assistant}]


def asr_rows(items: Iterable[dict], train: list[dict], decon: "Decontaminator", make_input,
             system: Optional[str], lost=None) -> tuple[list[dict], Counter]:
    """Training rows from measured Whisper transcripts (data/annotated/asr_f.jsonl, scripts/asr_layer.py): each kept
    transcript of a train line becomes one more row whose input is the transcript, with the source row's dispatch
    and speaker lines re-attached unchanged by `make_input(text, by, speaker, dispatch)`, and whose target is the
    source row's clean completion. The source is found by id, or by its text when ids moved (a rebuild with more
    data); only train lines are sources, so a line now in dev never gets a transcript in train (the dev split stays
    clean text). `lost(facts, said, heard)` re-checks the labels as built now against the transcript. A transcript
    that overlaps a held-out set, or whose line is not in train, is dropped and counted."""
    by_id = {r["id"]: r for r in train}
    by_text: dict[str, dict] = {}
    for r in train:
        by_text.setdefault(r["raw_text"], r)
    out: list[dict] = []
    counts: Counter = Counter()
    for it in items:
        if not it.get("kept"):
            counts[f"asr judged out: {it.get('reason', '?').split(':')[0]}"] += 1
            continue
        src = by_id.get(it["source_id"])
        if src is None or src["raw_text"] != it["raw_text"]:      # ids move when the data grows: match the line
            src = by_text.get(it["raw_text"])
        if src is None:
            counts["asr: source line not in train (in dev, or no longer built)"] += 1
            continue
        heard = it["whisper"].strip()
        if heard == src["raw_text"].strip():
            counts["asr: transcript identical to the clean line"] += 1
            continue
        if decon.overlaps(heard):
            counts["asr: overlaps a held-out set (8-word run or same words)"] += 1
            continue
        why = lost(json.loads(src["completion"])["f"], src["raw_text"], heard) if lost else None
        if why:             # the line's labels as built now (they can change after the transcript was judged)
            counts[f"asr: labels no longer supported ({why.split(':')[0]})"] += 1
            continue
        r = {"id": f"{src['id']}~asr{it['clip']}",
             "text": make_input(heard, src["by"], src["speaker"], src.get("dispatch")),
             "by": src["by"], "speaker": src["speaker"], "dispatch": src.get("dispatch"), "source": "asr",
             "completion": src["completion"], "raw_text": heard}
        if system is not None:
            r["messages"] = chat_messages(system, r["text"], r["completion"])
        out.append(r)
        counts[f"asr added: {it['condition']}"] += 1
    return out, counts
