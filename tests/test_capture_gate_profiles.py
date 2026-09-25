"""The monitor-watch gate profile admits a screen; the one-shot photo profile is unchanged.

The numbers asserted here come from scripts/capture/gate_probe.py (pure CPU, synthetic renders of a camera photo of
a laptop showing a monitor UI, 2026-09-25). They are engineering measurements of the gate, not clinical thresholds,
and synthetic renders understate `change` because real camera noise adds difference to every pixel.
"""
import pytest

from herald.capture.config import capture_config, monitor_gate_config, validate_config
from herald.capture.gate import FrameGate
from herald.capture.types import ROI

from test_capture_gate import frame

# Import the probe by path: scripts/ is not a package.
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gate_probe", Path(__file__).resolve().parents[1] / "scripts" / "capture" / "gate_probe.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

SCREEN_ROI_PAD = 0.0


def screen_pair(*, dark=True, vitals_changed=1):
    """A baseline photo and a second photo of the same screen with one or four vitals changed, plus the screen ROI."""
    width, height = 1280, 800
    first, box = probe.monitor_photo(96, 140, 88, 95, 18, dark=dark, width=width, height=height)
    if vitals_changed == 1:
        second, _ = probe.monitor_photo(96, 168, 94, 95, 18, dark=dark, width=width, height=height)
    else:
        second, _ = probe.monitor_photo(124, 168, 94, 91, 24, dark=dark, width=width, height=height)
    roi = probe.roi_from_box(box, width, height, SCREEN_ROI_PAD)
    return probe.as_frame(first, "a", 0.0), probe.as_frame(second, "b", 1.0), roi


def assess(profile, first, second, roi):
    gate = FrameGate(profile)
    gate.accept(first, roi)
    return gate.assess(second, roi)


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("vitals_changed", [1, 4])
def test_screen_roi_passes_the_monitor_profile(dark, vitals_changed):
    config = capture_config()
    first, second, roi = screen_pair(dark=dark, vitals_changed=vitals_changed)
    result = assess(monitor_gate_config(config), first, second, roi)
    assert result.usable and result.passed and result.reason == "changed"


@pytest.mark.parametrize("dark", [True, False])
def test_the_shipped_global_profile_cannot_see_a_screen(dark):
    """Why a separate profile exists: on the global values the screen ROI is not even `usable`, so neither
    monitor_changed nor monitor_refresh can ever run."""
    config = capture_config()
    first, second, roi = screen_pair(dark=dark, vitals_changed=1)
    result = assess(config["gate"], first, second, roi)
    assert not result.usable and result.reason == ("dark" if dark else "bright")
    full = assess(config["gate"], first, second, None)
    assert full.usable and not full.passed and full.changed < config["gate"]["change_min"]


def test_one_shot_photo_path_behaviour_is_unchanged():
    """The global profile still accepts, rejects and re-baselines exactly as tests/test_capture_gate.py asserts."""
    config = capture_config()
    assert config["gate"] == {"sharp_min": 60, "change_min": 0.06, "bright_min": 25, "bright_max": 235, "width": 320}
    gate = FrameGate(config["gate"])
    first = frame()
    assert gate.assess(first).passed
    gate.accept(first)
    assert gate.assess(first).reason == "unchanged"
    assert gate.assess(frame(offset=7)).passed
    assert gate.assess(frame(blur=True)).reason == "blurred"
    assert gate.assess(frame(brightness=20)).reason == "dark"      # inside the monitor profile, outside the global
    assert gate.assess(frame(brightness=240)).reason == "bright"   # same, at the top end


def test_monitor_profile_only_overrides_the_global_one():
    config = capture_config()
    profile = monitor_gate_config(config)
    assert profile["sharp_min"] == config["gate"]["sharp_min"] and profile["width"] == config["gate"]["width"]
    assert profile["change_min"] < config["gate"]["change_min"]
    assert profile["bright_min"] < config["gate"]["bright_min"] and profile["bright_max"] > config["gate"]["bright_max"]
    # Stability stays at the value it had before the profile existed, so nothing starves on camera noise.
    assert profile["stable_max"] == 0.06


def test_monitor_gate_overrides_are_validated():
    config = capture_config()
    config["monitor"]["gate"]["bright_min"] = 250          # above bright_max
    with pytest.raises(ValueError):
        validate_config(config)
    config = capture_config()
    config["monitor"]["gate"]["sharpness"] = 1             # not a gate threshold
    with pytest.raises(ValueError):
        validate_config(config)


def test_roi_on_a_dark_screen_admits_a_refresh_read():
    """`usable` is what monitor_refresh rides on (herald/capture/buffer.py `best(refresh=True)`)."""
    config = capture_config()
    first, second, roi = screen_pair(dark=True, vitals_changed=1)
    gate = FrameGate(monitor_gate_config(config))
    assert gate.assess(first, roi).usable
