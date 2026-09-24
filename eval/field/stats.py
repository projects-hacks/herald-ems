"""Bootstrap 95% confidence intervals for micro-F1 (summed counts, as the benchmark reports).

Every interval resamples whole units and recomputes F1 from the summed counts: clips for the clip-level interval,
and speakers for the cluster intervals, because clips from one person are not independent. With 5-6 people the
speaker intervals are the honest ones, and the quiet-minus-noise difference is always resampled by speaker. The
F1 here is unrounded; reported numbers use eval/visionbench/common.py's `prf`."""
from __future__ import annotations

import random
from typing import Iterable, Sequence

Counts = tuple[int, int, int]           # tp, fp, fn


def f1(counts: Iterable[Counts]) -> float:
    tp = fp = fn = 0
    for a, b, c in counts:
        tp, fp, fn = tp + a, fp + b, fn + c
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


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


def paired_difference(groups: dict[str, Sequence[tuple[Counts, Counts]]], n: int = 2000,
                      seed: int = 0) -> tuple[float, float, float]:
    """F1(first) - F1(second) over matched pairs (the same speaker and card in two conditions), with a 95% interval
    that resamples speakers and keeps all of each speaker's pairs: one or two people with a large noise effect
    widen the interval instead of making the difference look significant."""
    names = sorted(g for g in groups if groups[g])
    if not names:
        return 0.0, 0.0, 0.0
    pairs = [p for g in names for p in groups[g]]
    point = f1(a for a, _ in pairs) - f1(b for _, b in pairs)
    rng = random.Random(seed)
    k = len(names)
    diffs = []
    for _ in range(n):
        sample = [p for _ in range(k) for p in groups[names[rng.randrange(k)]]]
        diffs.append(f1(a for a, _ in sample) - f1(b for _, b in sample))
    lo, hi = _interval(diffs)
    return round(point, 3), lo, hi
