"""The soak's memory verdict (scripts/soak.py summarize()).

Why this file exists. The soak judged memory with `used[-1] - used[0]`: two instantaneous samples 30 minutes apart.
On the GB10, MemAvailable includes reclaimable page cache and is lowered by CUDA allocations that are not charged to a
cgroup (AGENTS.md), so the trace is a mean-reverting sawtooth. A measured 30-minute run dipped and recovered between
22.2 and 31.9 GiB free with a standard deviation of 2.95 GiB, and its endpoint difference of +2.14 GiB -- 0.73 standard
deviations, less than the noise -- failed the check while the trend over all 61 samples was downward in memory used.

A pass criterion was changed because of that, which is the kind of change that deserves suspicion. So these tests do
the thing that separates a justified change from a moved goalpost: they feed traces whose answer is known in advance
and assert the new statistics still FAIL a leak. A check that cannot fail would be worse than the one it replaced.
"""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import soak  # noqa: E402

GIB = 1024 ** 3


def trace(kind: str, n: int = 61, minutes: float = 30.0) -> list[dict]:
    """`used` bytes over time, as summarize() reads them. A leak means `used` goes UP."""
    base = 90.0 * GIB
    out = []
    for i in range(n):
        t = i * (minutes * 60.0 / (n - 1))
        frac = i / (n - 1)
        saw = 4.0 * GIB * abs(math.sin(i * 0.7))              # +-4 GiB, mean reverting, no trend
        used = {
            "flat": base,
            "leak": base + 3.0 * GIB * frac,                   # 3 GiB consumed, no noise
            "sawtooth": base + saw,                            # noise, no trend
            "leak_in_sawtooth": base + 3.0 * GIB * frac + saw,  # 3 GiB leak hidden in the noise
            "slow_leak": base + 1.5 * GIB * frac,               # 1.5 GiB over 30 min = 3 GiB/hour
            "freed": base - 2.0 * GIB * frac,                   # gave memory back
        }[kind]
        out.append({"type": "sample", "elapsed_s": t,
                    "memory": {"used_bytes": int(used), "available_bytes": int(130 * GIB - used)},
                    "competing_jobs": []})
    return out


def summary_for(kind: str, **extra) -> dict:
    events = trace(kind)
    events.append({"type": "iteration", "elapsed_s": 1800.0, "iteration": 1, "relay_failures": 0})
    events.append({"type": "model", "elapsed_s": 10.0, "status": "done", "latency_ms": 1000.0})
    events.append({"type": "model", "elapsed_s": 1700.0, "status": "done", "latency_ms": 1000.0})
    events.extend(extra.get("events", []))
    return soak.summarize(events, 1800.0, 1800.0)


# ── the statistics must catch a leak ──
@pytest.mark.parametrize("kind", ["leak", "leak_in_sawtooth"])
def test_a_three_gib_leak_fails_both_trend_checks(kind):
    """3 GiB over 30 minutes, with and without +-4 GiB of sawtooth on top of it."""
    c = summary_for(kind)["checks"]
    assert not c["memory_growth_within_1_gib"], f"{kind}: the median-of-thirds check missed a 3 GiB leak"
    assert not c["memory_slope_within_2_gib_per_hour"], f"{kind}: the slope check missed a 3 GiB leak"


def test_a_leak_just_over_the_bar_fails_the_slope_check():
    """1.5 GiB per half hour is 3 GiB/hour, over the 2 GiB/hour bar: the boundary must bite, not round away."""
    c = summary_for("slow_leak")["checks"]
    assert not c["memory_slope_within_2_gib_per_hour"]


# ── and must not fire on noise ──
@pytest.mark.parametrize("kind", ["flat", "sawtooth", "freed"])
def test_trend_free_traces_pass(kind):
    c = summary_for(kind)["checks"]
    assert c["memory_growth_within_1_gib"], f"{kind}: trend check fired without a trend"
    assert c["memory_slope_within_2_gib_per_hour"], f"{kind}: slope check fired without a trend"


def test_the_sawtooth_is_what_broke_the_old_endpoint_check():
    """The reason for the change, asserted rather than described: the same trend-free trace that the new checks clear
    is one the old endpoint statistic gets wrong, because its answer depends on where the cycle starts and stops."""
    m = summary_for("sawtooth")["memory"]
    assert m["trend_growth_bytes"] <= GIB                      # no trend, correctly
    assert not m["endpoint_growth_within_1_gib"]               # yet the endpoint difference says otherwise
    assert m["noise_stdev_bytes"] > GIB                         # because the trace's own noise is larger than the bar


def test_the_old_endpoint_number_is_still_reported():
    """The change must be auditable: the previous statistic stays in the output, with its size in units of the noise."""
    m = summary_for("sawtooth")["memory"]
    for key in ("final_growth_bytes", "peak_growth_bytes", "endpoint_growth_within_1_gib",
                "endpoint_growth_in_stdevs", "trend_growth_bytes", "slope_bytes_per_hour", "noise_stdev_bytes"):
        assert key in m, f"{key} missing: the memory verdict is no longer auditable"


# ── the rest of the verdict must be untouched by this change ──
def test_a_model_error_still_fails_the_run_on_a_clean_memory_trace():
    """The control. If relaxing the memory statistic had made runs pass in general, this would pass too -- and the
    recorded soak that contained a real /api/state 500 must still be judged a failure."""
    s = summary_for("flat", events=[{"type": "model", "elapsed_s": 195.0, "status": "timeout",
                                     "latency_ms": None, "error": "500 Internal Server Error"}])
    assert not s["checks"]["model_errors_zero"]
    assert not s["passed"], "a run with a model error must not pass, however healthy its memory trace is"


def test_the_two_recorded_soaks_score_as_expected():
    """Against the real files, if they are present: the pre-fix run fails on its model error, the post-fix run passes."""
    pre, post = ROOT / "runs/soak/ship_soak.jsonl", ROOT / "runs/soak/ship_soak2.jsonl"
    if not (pre.exists() and post.exists()):
        pytest.skip("soak recordings are under runs/, which is not committed")
    a = soak.summarize_recorded(pre)
    b = soak.summarize_recorded(post)
    assert a["model_errors"] == 1 and not a["passed"], "the pre-fix soak must still fail: it had a real 500"
    assert b["model_errors"] == 0 and b["passed"], "the post-fix soak must pass: 0 errors and no memory trend"
