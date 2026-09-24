"""Precision/recall/F1 from counts, and bootstrap 95% confidence intervals.

Every interval resamples whole units and recomputes F1 from the summed counts (micro-F1, as the benchmark reports):
clips for the clip-level interval, speakers for the cluster interval (clips from one person are not independent, so
this is the honest one when there are few speakers), and (quiet, noise) clip pairs for the condition difference."""
from __future__ import annotations

import random
from typing import Iterable, Sequence

Counts = tuple[int, int, int]           # tp, fp, fn


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def f1(counts: Iterable[Counts]) -> float:
    tp = fp = fn = 0
    for a, b, c in counts:
        tp, fp, fn = tp + a, fp + b, fn + c
    return prf(tp, fp, fn)[2]


def _interval(values: list[float]) -> tuple[float, float]:
    values = sorted(values)
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(0.975 * (len(values) - 1))]
    return round(lo, 3), round(hi, 3)


def bootstrap_f1(units: Sequence[Counts], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% interval for micro-F1, resampling units (clips) with replacement."""
    if not units:
        return 0.0, 0.0
    rng = random.Random(seed)
    k = len(units)
    return _interval([f1(units[rng.randrange(k)] for _ in range(k)) for _ in range(n)])


def cluster_bootstrap_f1(groups: dict[str, Sequence[Counts]], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% interval for micro-F1, resampling whole groups (speakers) with replacement."""
    names = sorted(groups)
    if not names:
        return 0.0, 0.0
    rng = random.Random(seed)
    k = len(names)
    return _interval([f1(c for _ in range(k) for c in groups[names[rng.randrange(k)]]) for _ in range(n)])


def paired_difference(pairs: Sequence[tuple[Counts, Counts]], n: int = 2000,
                      seed: int = 0) -> tuple[float, float, float]:
    """F1(first) - F1(second) over matched pairs (the same speaker and card in two conditions), with a 95% interval
    from resampling the pairs."""
    if not pairs:
        return 0.0, 0.0, 0.0
    point = f1(a for a, _ in pairs) - f1(b for _, b in pairs)
    rng = random.Random(seed)
    k = len(pairs)
    diffs = []
    for _ in range(n):
        sample = [pairs[rng.randrange(k)] for _ in range(k)]
        diffs.append(f1(a for a, _ in sample) - f1(b for _, b in sample))
    lo, hi = _interval(diffs)
    return round(point, 3), lo, hi
