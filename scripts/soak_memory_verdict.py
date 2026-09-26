#!/usr/bin/env python3
"""Re-score a soak's memory trace, and prove the scoring can still fail.

scripts/soak.py judges memory with `final_growth = used[-1] - used[0]`: two instantaneous samples, 30 minutes apart.
On the GB10 `MemAvailable` includes reclaimable page cache and is lowered by CUDA allocations that are not charged to
a cgroup (AGENTS.md), so the trace is a sawtooth that dips several GiB and fully recovers. Differencing two endpoints
of a sawtooth measures which part of the cycle the run happened to stop in.

This script reports three verdicts side by side on the SAME recorded samples, so nothing is replaced:

  endpoint   what soak.py does now: used[-1] - used[0] <= 1 GiB
  halves     median of the last third against the median of the first third
  slope      least-squares slope of used bytes over elapsed time, extrapolated to an hour

The point of the exercise is NOT to get a pass. A statistic that cannot fail is worthless, so --self-test injects
synthetic traces -- a real leak, a sawtooth with no trend, and a leak hidden inside a sawtooth -- and asserts that
`halves` and `slope` catch the leaks and clear the noise. If they do not, they are the wrong statistics and the
endpoint check should stand.

  python scripts/soak_memory_verdict.py --self-test
  python scripts/soak_memory_verdict.py runs/soak/ship_soak.jsonl runs/soak/ship_soak2.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from pathlib import Path

GIB = 1024 ** 3
HOUR = 3600.0
# Both bars are stated before looking at any real trace, and both are derived from soak.py's existing intent: "the app
# must not consume more than a GiB over a 30-minute run". A leak of 1 GiB per half hour is 2 GiB/hour, so a slope bar
# of -2 GiB/hour is the same severity expressed as a rate. The halves bar is the same 1 GiB, measured between medians
# instead of endpoints.
SLOPE_BAR_GIB_PER_HOUR = -2.0
HALVES_BAR_GIB = 1.0


def samples(path: Path) -> list[tuple[float, int]]:
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("type") == "sample" and r.get("memory"):
            out.append((float(r["elapsed_s"]), int(r["memory"]["used_bytes"])))
    return out


def slope_per_hour(xs: list[float], ys: list[float]) -> float:
    """Least-squares slope of used bytes per second, returned as GiB/hour. Positive = using more over time."""
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom) * HOUR / GIB


def verdicts(trace: list[tuple[float, int]]) -> dict:
    xs = [t for t, _ in trace]
    used = [float(u) for _, u in trace]
    n = len(used)
    third = max(1, n // 3)
    endpoint = (used[-1] - used[0]) / GIB
    halves = (st.median(used[-third:]) - st.median(used[:third])) / GIB
    sl = slope_per_hour(xs, used)
    noise = st.stdev([u / GIB for u in used]) if n > 1 else 0.0
    return {
        "samples": n,
        "noise_stdev_gib": round(noise, 2),
        "endpoint_growth_gib": round(endpoint, 2),
        "halves_growth_gib": round(halves, 2),
        "slope_gib_per_hour": round(sl, 2),
        # signal-to-noise of the endpoint statistic: how many standard deviations the "growth" actually is
        "endpoint_in_stdevs": round(endpoint / noise, 2) if noise else None,
        "pass_endpoint": endpoint <= 1.0,
        "pass_halves": halves <= HALVES_BAR_GIB,
        "pass_slope": sl <= -SLOPE_BAR_GIB_PER_HOUR * -1 if False else sl <= abs(SLOPE_BAR_GIB_PER_HOUR),
    }


def synth(kind: str, n: int = 61, minutes: float = 30.0) -> list[tuple[float, int]]:
    """Traces with a known answer, in `used` bytes (so a leak means used goes UP)."""
    base = 90.0 * GIB
    out = []
    for i in range(n):
        t = i * (minutes * 60.0 / (n - 1))
        frac = i / (n - 1)
        saw = 4.0 * GIB * abs(math.sin(i * 0.7))          # +-4 GiB sawtooth, mean-reverting, no trend
        if kind == "leak":                                # 3 GiB consumed over the run, no noise
            used = base + 3.0 * GIB * frac
        elif kind == "sawtooth":                          # noisy, no trend
            used = base + saw
        elif kind == "leak_in_sawtooth":                   # 3 GiB leak buried in the same noise
            used = base + 3.0 * GIB * frac + saw
        elif kind == "sawtooth_lucky_end":                # no trend, but it stops at the bottom of a dip
            used = base + saw - (3.5 * GIB if i == n - 1 else 0)
        else:
            raise ValueError(kind)
        out.append((t, int(used)))
    return out


def self_test() -> int:
    # `endpoint` is deliberately NOT asserted on any noisy trace. That is the whole finding: on a sawtooth its answer
    # is set by which part of the cycle the run starts and stops in, so it has no stable expectation to assert. On the
    # two traces below it happens to FAIL a trend-free sawtooth and PASS one that merely stops in a dip -- a false
    # failure and a false pass on the same statistic, from the same generator.
    cases = [
        # kind,                 endpoint should, halves should, slope should
        ("leak",                False, False, False),   # no noise at all: every statistic must catch it
        ("sawtooth",            None,  True,  True),    # no trend: halves and slope must clear it
        ("leak_in_sawtooth",    None,  False, False),   # 3 GiB leak buried in +-4 GiB of noise: must still be caught
        ("sawtooth_lucky_end",  None,  True,  True),    # no trend, stops in a dip
    ]
    bad = 0
    print(f"{'trace':22} {'endpoint':>9} {'halves':>8} {'slope/h':>9}   verdicts (endpoint/halves/slope)")
    for kind, want_e, want_h, want_s in cases:
        v = verdicts(synth(kind))
        print(f"{kind:22} {v['endpoint_growth_gib']:>9} {v['halves_growth_gib']:>8} "
              f"{v['slope_gib_per_hour']:>9}   "
              f"{'pass' if v['pass_endpoint'] else 'FAIL'}/"
              f"{'pass' if v['pass_halves'] else 'FAIL'}/"
              f"{'pass' if v['pass_slope'] else 'FAIL'}")
        for name, got, want in (("endpoint", v["pass_endpoint"], want_e),
                                ("halves", v["pass_halves"], want_h),
                                ("slope", v["pass_slope"], want_s)):
            if want is not None and got != want:
                print(f"    !! {name} on '{kind}' returned {'pass' if got else 'FAIL'}, expected "
                      f"{'pass' if want else 'FAIL'}")
                bad += 1
    print()
    if bad:
        print(f"SELF-TEST FAILED: {bad} expectation(s) wrong. These statistics are not trustworthy; the endpoint "
              f"check should stand.")
    else:
        print("SELF-TEST PASSED: halves and slope FAIL a 3 GiB leak, FAIL a leak buried in +-4 GiB of sawtooth, and "
              "PASS pure sawtooth -- including a trace that stops in a dip, where the endpoint check passes by luck.")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(1 if self_test() else 0)
    if not a.files:
        ap.error("give one or more soak jsonl files, or --self-test")
    for f in a.files:
        tr = samples(f)
        if not tr:
            print(f"{f}: no memory samples")
            continue
        v = verdicts(tr)
        print(f"=== {f}  ({v['samples']} samples, trace stdev {v['noise_stdev_gib']} GiB)")
        print(f"  endpoint  used[-1]-used[0] = {v['endpoint_growth_gib']:+.2f} GiB  "
              f"({v['endpoint_in_stdevs']} stdevs of the trace's own noise)  "
              f"-> {'pass' if v['pass_endpoint'] else 'FAIL'}   [what soak.py reports today]")
        print(f"  halves    median(last 1/3) - median(first 1/3) = {v['halves_growth_gib']:+.2f} GiB  "
              f"-> {'pass' if v['pass_halves'] else 'FAIL'}")
        print(f"  slope     {v['slope_gib_per_hour']:+.2f} GiB/hour of memory USED  "
              f"-> {'pass' if v['pass_slope'] else 'FAIL'}")


if __name__ == "__main__":
    main()
