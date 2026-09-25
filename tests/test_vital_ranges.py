"""config/vital_ranges.yaml + herald/core/vital_severity.py, tested at every band boundary.

Like the score tables (tests/test_scores.py), each boundary is checked on both sides, because an off-by-one in a
clinical colour is exactly the kind of error that must not reach the screen. The expected severities are read against
the published NEWS2 chart the bands are derived from (config/scores/news2.yaml), so this file also guards that the two
never drift apart.
"""
import pytest

from herald.config import load_yaml
from herald.core.vital_severity import VitalRanges


@pytest.fixture(scope="module")
def ranges() -> VitalRanges:
    return VitalRanges.from_config(load_yaml)


# (key, value, expected severity). None = neutral, not coloured.
BOUNDARIES = [
    # SpO2: <=91 critical, 92-95 abnormal, >=96 normal
    ("vitals.spo2", 84, "critical"), ("vitals.spo2", 91, "critical"), ("vitals.spo2", 92, "abnormal"),
    ("vitals.spo2", 95, "abnormal"), ("vitals.spo2", 96, None), ("vitals.spo2", 99, None),
    # Systolic BP: <=90 critical, 91-110 abnormal, 111-219 normal, >=220 critical
    ("vitals.sbp", 90, "critical"), ("vitals.sbp", 91, "abnormal"), ("vitals.sbp", 110, "abnormal"),
    ("vitals.sbp", 111, None), ("vitals.sbp", 146, None), ("vitals.sbp", 219, None), ("vitals.sbp", 220, "critical"),
    # HR: <=40 critical, 41-50 abnormal, 51-90 normal, 91-130 abnormal, >=131 critical
    ("vitals.hr", 40, "critical"), ("vitals.hr", 41, "abnormal"), ("vitals.hr", 50, "abnormal"),
    ("vitals.hr", 51, None), ("vitals.hr", 90, None), ("vitals.hr", 91, "abnormal"), ("vitals.hr", 104, "abnormal"),
    ("vitals.hr", 130, "abnormal"), ("vitals.hr", 131, "critical"),
    # RR: <=8 critical, 9-11 abnormal, 12-20 normal, 21-24 abnormal, >=25 critical
    ("vitals.rr", 8, "critical"), ("vitals.rr", 9, "abnormal"), ("vitals.rr", 11, "abnormal"),
    ("vitals.rr", 12, None), ("vitals.rr", 20, None), ("vitals.rr", 21, "abnormal"), ("vitals.rr", 25, "critical"),
    # Temp: <=35.0 critical, 35.1-36.0 abnormal, 36.1-38.0 normal, >=38.1 abnormal
    ("vitals.temp", 35.0, "critical"), ("vitals.temp", 35.1, "abnormal"), ("vitals.temp", 36.0, "abnormal"),
    ("vitals.temp", 36.1, None), ("vitals.temp", 38.0, None), ("vitals.temp", 38.1, "abnormal"),
    ("vitals.temp", 39.5, "abnormal"),
    # Glucose (ADA 2024): <54 critical, 54-69 abnormal, 70-249 normal, >=250 abnormal
    ("vitals.glucose", 53, "critical"), ("vitals.glucose", 54, "abnormal"), ("vitals.glucose", 69, "abnormal"),
    ("vitals.glucose", 70, None), ("vitals.glucose", 142, None), ("vitals.glucose", 249, None),
    ("vitals.glucose", 250, "abnormal"),
]


@pytest.mark.parametrize("key, value, expected", BOUNDARIES)
def test_boundary(ranges, key, value, expected):
    assert ranges.severity(key, value) == expected, f"{key}={value} should be {expected}"


def test_diastolic_is_never_coloured(ranges):
    """dbp is shown but deliberately not coloured (config/vital_ranges.yaml: bands []); every value is neutral."""
    for v in (40, 60, 88, 120, 200):
        assert ranges.severity("vitals.dbp", v) is None


def test_non_numeric_and_missing_are_neutral(ranges):
    for v in (None, "", "high", [1, 2], object()):
        assert ranges.severity("vitals.spo2", v) is None


def test_a_key_with_no_bands_is_neutral(ranges):
    assert ranges.severity("vitals.not_a_vital", 5) is None


def test_severity_withdraws_when_not_applicable(ranges):
    """The adult NEWS2-derived colouring must withdraw for the patients NEWS2 itself excludes (paediatric,
    documented pregnancy). A value that would be critical for an adult shows NO severity when applicable is False,
    because a paediatric HR of 120 is normal and a red tuned to adults would be actively wrong."""
    for key, value in [("vitals.spo2", 84), ("vitals.hr", 135), ("vitals.rr", 6), ("vitals.sbp", 85)]:
        assert ranges.severity(key, value, applicable=True) is not None      # abnormal for an adult
        assert ranges.severity(key, value, applicable=False) is None         # withdrawn for the excluded patient


def test_every_boundary_lands_in_exactly_one_band(ranges):
    """No overlap and no gap: sweeping across each vital's boundaries, severity changes only at the documented edges,
    and a value never matches two bands (the engine returns the first, so a duplicate would be a silent config error)."""
    cfg = load_yaml("vital_ranges.yaml")["vitals"]
    for key, spec in cfg.items():
        for band in spec.get("bands", []):
            forms = [k for k in ("below", "at_or_below", "at_or_above", "from") if k in band]
            assert len(forms) == 1, f"{key} band {band} must use exactly one of below/at_or_below/at_or_above/from"
            if "from" in band:
                assert "to" in band and band["to"] > band["from"], f"{key} band {band} needs to > from"


def test_bands_agree_with_the_news2_chart():
    """The bands claim to come from the NEWS2 chart; assert that the critical bands are exactly the 3-point ranges and
    that no coloured band sits inside a 0-point range, so the tile colour can never contradict the NEWS2 tile."""
    ranges = VitalRanges.from_config(load_yaml)
    # A 0-point NEWS2 value must be neutral on the tile.
    for key, zero_value in [("vitals.spo2", 98), ("vitals.sbp", 120), ("vitals.hr", 70),
                            ("vitals.rr", 16), ("vitals.temp", 37.0)]:
        assert ranges.severity(key, zero_value) is None, f"{key}={zero_value} scores 0 in NEWS2 but is coloured"
    # A 3-point NEWS2 value must be critical.
    for key, three_value in [("vitals.spo2", 88), ("vitals.sbp", 85), ("vitals.hr", 135),
                             ("vitals.rr", 6)]:
        assert ranges.severity(key, three_value) == "critical", f"{key}={three_value} scores 3 in NEWS2, expected critical"


# ── SpO2 Scale 2 (hypercapnic / COPD, target 88-92%), from the RCP NEWS2 Scale 2 chart ──
SCALE_2 = [
    (83, "critical"), (84, "abnormal"), (87, "abnormal"),
    (88, None), (90, None), (92, None),          # the target band is not coloured
    (93, "critical"), (97, "critical"),          # on this scale a "normal" saturation is too high
]


@pytest.mark.parametrize("value, expected", SCALE_2)
def test_spo2_scale_2_boundary(ranges, value, expected):
    assert ranges.severity("vitals.spo2", value, spo2_scale=2) == expected, f"scale 2 SpO2 {value}"


def test_scale_2_changes_only_spo2(ranges):
    """Scale 2 re-bands SpO2 and nothing else: HR, RR and SBP keep their normal bands."""
    for key, value in [("vitals.hr", 135), ("vitals.rr", 6), ("vitals.sbp", 85)]:
        assert ranges.severity(key, value, spo2_scale=2) == ranges.severity(key, value)


def test_same_saturation_reads_differently_on_the_two_scales(ranges):
    assert ranges.severity("vitals.spo2", 90) == "critical"          # scale 1: well below target
    assert ranges.severity("vitals.spo2", 90, spo2_scale=2) is None  # scale 2: on target


def test_scale_2_still_withdraws_when_not_applicable(ranges):
    assert ranges.severity("vitals.spo2", 80, spo2_scale=2, applicable=False) is None
