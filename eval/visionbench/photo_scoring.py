"""Scoring photo readings against eval/photos/gold.jsonl (pure functions, no model calls).

An atom is (key, normalized value), as in eval/bench_extract.py (scorer v2): list facts give one atom per item;
numbers compare after rounding to one decimal; strings compare lowercased without spaces and periods. Drug names
are not normalized by the scorer. Free-text keys (scene.notes) are scored by key presence only.

Three views of the same predictions:
- lenient (headline): a gold atom also accepts the aliases printed on the item (brand names on a label, the
  option text on a form), because the photo prompt asks for "generic or brand" and "exactly as printed";
- strict: only the LABELING_GUIDE canonical value (generic drug name, "DNR"/"full code");
- in-prompt scope: gold and predictions restricted to keys the mode prompt names (plus keys the reader derives),
  so keys the prompt never asks for (glucose, temperature on the monitor prompt) don't dominate the comparison.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional

from eval.bench_extract import FREE_TEXT, KEYS, norm
from eval.visionbench.common import prf

# VisionReader adds meds.anticoagulant itself whenever meds.list names one (herald/models/vision.py).
DERIVED_KEYS = {"meds.list": ("meds.anticoagulant",)}

Atom = tuple[str, object]


def _norm_item(key: str, v) -> object:
    return norm(key, " ".join(str(v).split()) if isinstance(v, str) else v)


def atoms(facts: Iterable[tuple[str, object]]) -> list[Atom]:
    """(key, value) facts -> atoms; list values give one atom per item; free-text keys give (key, None)."""
    out: list[Atom] = []
    for k, v in facts:
        if k in FREE_TEXT:
            out.append((k, None))
        elif KEYS.get(k, {}).get("type") == "list" or isinstance(v, list):
            items = v if isinstance(v, list) else [v]
            out += [(k, _norm_item(k, x)) for x in items] or [(k, "<none>")]
        else:
            out.append((k, _norm_item(k, v)))
    return list(dict.fromkeys(out))


def scope_keys(prompt: str) -> set[str]:
    """Vocabulary keys a mode prompt names, plus the keys the reader derives from them."""
    named = {k for k in KEYS if re.search(rf"(?<![\w.]){re.escape(k)}(?![\w.])", prompt)}
    return named | {d for k in named for d in DERIVED_KEYS.get(k, ())}


def match(gold: list, aliases: dict, pred: list, lenient: bool = True, keep: Optional[set] = None) -> dict:
    """Greedy one-to-one matching of predicted atoms to gold atoms. Returns counts and the unmatched atoms."""
    g_atoms = [a for a in atoms(gold) if keep is None or a[0] in keep]
    p_atoms = [a for a in atoms(pred) if keep is None or a[0] in keep]
    accepted = []
    for k, v in g_atoms:
        ok = {v}
        if lenient and v is not None:
            ok |= {_norm_item(k, a) for a in aliases.get(k, [])}
        accepted.append((k, ok))
    used, extra = set(), []
    for k, v in p_atoms:
        hit = next((i for i, (gk, ok) in enumerate(accepted) if i not in used and gk == k and v in ok), None)
        if hit is None:
            extra.append([k, v])
        else:
            used.add(hit)
    missed = [list(a) for i, a in enumerate(g_atoms) if i not in used]
    return {"tp": len(used), "fp": len(extra), "fn": len(missed), "extra": extra, "missed": missed}


def strength_ok(gold_strength: Optional[str], texts: list[str]) -> Optional[bool]:
    """Whether the strength printed on the label ("5 MG") is in the reader's provenance text ("warfarin 5 mg")."""
    if not gold_strength:
        return None
    want = re.sub(r"\s+", "", gold_strength.lower())
    return any(want in re.sub(r"\s+", "", (t or "").lower()) for t in texts)


def score_item(line: dict, pred: list, prompt: str) -> dict:
    """All views for one image."""
    aliases = line.get("aliases", {})
    structured = {k for k, _ in line["facts"] + pred if k not in FREE_TEXT}
    free = {k for k, _ in line["facts"] + pred if k in FREE_TEXT}
    s = {"lenient": match(line["facts"], aliases, pred, True, structured),
         "strict": match(line["facts"], aliases, pred, False, structured),
         "scope": match(line["facts"], aliases, pred, True, scope_keys(prompt) - FREE_TEXT),
         "free_text": match(line["facts"], aliases, pred, True, free)}
    s["exact"] = s["lenient"]["fp"] == 0 and s["lenient"]["fn"] == 0 and s["free_text"]["fp"] == 0 \
        and s["free_text"]["fn"] == 0
    s["no_fact_image"] = not line["facts"]
    s["false_fact"] = s["no_fact_image"] and s["lenient"]["fp"] > 0
    return s


def _sum(items: list[dict], view: str) -> dict:
    return prf(sum(i["score"][view]["tp"] for i in items), sum(i["score"][view]["fp"] for i in items),
               sum(i["score"][view]["fn"] for i in items))


def _group(items: list[dict]) -> dict:
    out = {"n": len(items), **{k: v for k, v in _sum(items, "lenient").items() if k in ("precision", "recall", "f1")},
           "exact_image_acc": round(sum(i["score"]["exact"] for i in items) / len(items), 3) if items else None}
    free = _sum(items, "free_text")
    if free["tp"] + free["fp"] + free["fn"]:
        out["free_text_presence_f1"] = free["f1"]
    return out


def aggregate(items: list[dict]) -> dict:
    """Run-level metrics from per-image records (each has 'line', 'score', 'error', 'json_invalid')."""
    by_mode, by_deg, by_key = defaultdict(list), defaultdict(list), defaultdict(lambda: [0, 0, 0])
    for it in items:
        by_mode[it["line"]["mode"]].append(it)
        for d in it["line"]["degradations"] or ["clean"]:
            by_deg[d].append(it)
        for k, _ in it["score"]["lenient"]["extra"]:
            by_key[k][1] += 1
        for k, _ in it["score"]["lenient"]["missed"]:
            by_key[k][2] += 1
        for k, v in atoms([f for f in it["line"]["facts"] if f[0] not in FREE_TEXT]):
            if [k, v] not in it["score"]["lenient"]["missed"]:
                by_key[k][0] += 1
    no_fact = [i for i in items if i["score"]["no_fact_image"]]
    strength = [i["strength_ok"] for i in items if i.get("strength_ok") is not None]
    head = _sum(items, "lenient")
    return {
        "n": len(items), "precision": head["precision"], "recall": head["recall"], "f1": head["f1"],
        "counts": {k: head[k] for k in ("tp", "fp", "fn")},
        "strict_f1": _sum(items, "strict")["f1"], "in_prompt_scope_f1": _sum(items, "scope")["f1"],
        "free_text_presence_f1": _sum(items, "free_text")["f1"],
        "exact_image_acc": round(sum(i["score"]["exact"] for i in items) / len(items), 3) if items else None,
        "no_fact_images": len(no_fact), "false_fact_images": sum(i["score"]["false_fact"] for i in no_fact),
        "strength_acc": round(sum(strength) / len(strength), 3) if strength else None,
        "json_invalid": sum(bool(i["json_invalid"]) for i in items),
        "errors": sum(bool(i["error"]) and not i["json_invalid"] for i in items),
        "per_mode": {m: _group(v) for m, v in sorted(by_mode.items())},
        "per_degradation": {d: _group(v) for d, v in sorted(by_deg.items())},
        "per_key": {k: prf(*v) for k, v in sorted(by_key.items())},
    }
