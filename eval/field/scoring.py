"""Score one clip's extracted facts against its card, with the benchmark's own atoms (eval/bench_extract.py).

- headline: the gold-v2 headline definition (structured keys outside the separately scored groups), so field
  numbers sit next to the held-out numbers;
- all keys: every key on the card, free-text keys by presence (paraphrase is not an error);
- per key: counts for the per-key precision/recall table;
- missed facts: card facts not fully recovered (list keys item by item), for the omission review.

A human reviewer, listening to the clip, can mark card facts the speaker never said (`omitted`); those are removed
from the gold for the "said" score, reported beside the "as carded" score, never instead of it. The review covers
every card fact and never shows model output, so the "said" gold is the same for every model and run."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from eval.bench_extract import KEYS, group_atoms, score
from herald.core.vocabulary import Vocabulary

Fact = tuple                        # (key, value, role)


def fact_id(key: str, value) -> str:
    """How a card fact is named in the omission review: key and value, canonical JSON."""
    return json.dumps([key, value], sort_keys=True)


@dataclass
class ClipScore:
    headline: list[int]             # tp, fp, fn, role_ok
    all_keys: list[int]             # tp, fp, fn, role_ok
    per_key: dict[str, list[int]] = field(default_factory=dict)      # key -> tp, fp, fn
    missed_facts: list[list] = field(default_factory=list)            # [key, value, role] from the card
    extra: list[list] = field(default_factory=list)                   # predicted atoms not on the card

    def to_json(self) -> dict:
        return {"headline": self.headline, "all_keys": self.all_keys, "per_key": self.per_key,
                "missed_facts": self.missed_facts, "extra": self.extra}


def itemize(facts: Iterable[Fact]) -> list[Fact]:
    """List facts one item at a time (the scorer's atoms are per item anyway), so a reviewer can mark one medication
    as never said without dropping the others."""
    out = []
    for k, v, r in facts:
        if KEYS.get(k, {}).get("type") == "list" and isinstance(v, list) and v:
            out += [(k, [x], r) for x in v]
        else:
            out.append((k, v, r))
    return out


def omission_ids(card_facts: Iterable[Fact], entries: Iterable, vocab: Vocabulary) -> tuple[set[str], list]:
    """The reviewer's `omitted` entries for one clip as fact ids, each normalized the way the card is (72.0 -> 72).
    Entries that match no fact on the card come back separately, so the bench warns instead of ignoring them."""
    valid = {fact_id(k, v) for k, v, _ in itemize(card_facts)}
    ids, unmatched = set(), []
    for e in entries:
        try:
            fid = fact_id(e[0], vocab.validate(e[0], e[1]))
        except (ValueError, IndexError, TypeError, KeyError):
            fid = None
        if fid in valid:
            ids.add(fid)
        else:
            unmatched.append(e)
    return ids, unmatched


def score_clip(card_facts: Iterable[Fact], pred: list[Fact], omitted: Iterable[str] = ()) -> ClipScore:
    omitted = set(omitted)
    gold = [f for f in itemize(card_facts) if fact_id(f[0], f[1]) not in omitted]
    tp, fp, fn, role_ok, _, _ = score(gold, pred)
    g, p = group_atoms(gold), group_atoms(pred)
    hits = set(g) & set(p)
    per_key: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for a in hits:
        per_key[a[0]][0] += 1
    for a in set(p) - hits:
        per_key[a[0]][1] += 1
    for a in set(g) - hits:
        per_key[a[0]][2] += 1
    missed = [list(f) for f in gold if not set(group_atoms([f])) <= set(p)]
    return ClipScore(headline=[tp, fp, fn, role_ok],
                     all_keys=[len(hits), len(p) - len(hits), len(g) - len(hits), sum(g[a] == p[a] for a in hits)],
                     per_key=dict(per_key), missed_facts=missed,
                     extra=[[str(x) for x in a] for a in sorted(set(p) - hits, key=str)])
