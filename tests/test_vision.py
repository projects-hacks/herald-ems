"""Photo reading is about the measurement, not the device: whatever screen the photo shows (a bedside monitor, a
smartwatch, a phone health app), every reading the vision model returns goes through the same checks (canonical
key, the tighter photo plausibility ranges, the SBP/DBP order) and starts unconfirmed until the medic taps it."""
import re

import pytest

from fakes import FakeModel, make_client
from herald.config import load_yaml
from herald.core.schema import CapturedBy, Role
from herald.core.vocabulary import default_vocabulary
from herald.models import VisionReader

CFG = load_yaml("prompts/vision.yaml")
VOCAB = default_vocabulary()


class ScreenModel:
    """A vision-model stand-in that answers every photo with the given facts."""

    def __init__(self, facts: list[dict]):
        self.facts = facts

    def available(self):
        return True

    def model_name(self):
        return "fake-vision"

    def chat_json(self, system, user, **kw):
        return {"facts": [dict(f) for f in self.facts]}


def read(facts: list[dict], mode: str = "monitor") -> dict:
    return {f.key: f.value for f in VisionReader(ScreenModel(facts)).read(b"jpg", mode)}


def test_every_photo_range_is_a_canonical_numeric_key_inside_its_vocabulary_range():
    for key, (lo, hi) in CFG["plausible_ranges"].items():
        meta = VOCAB.meta(key)
        assert meta.get("type") in ("int", "float"), key
        vlo, vhi = meta["range"]
        assert vlo <= lo < hi <= vhi, key


def test_every_numeric_key_a_mode_can_return_has_a_photo_range():
    """A key a photo prompt asks for (whatever device the value is on) is range-checked like every other."""
    for mode, prompt in CFG["modes"].items():
        for key, meta in VOCAB.keys.items():
            named = re.search(rf"(?<![\w.]){re.escape(key)}(?![\w.])", prompt)
            if named and meta.get("type") in ("int", "float"):
                assert key in CFG["plausible_ranges"], (mode, key)


# Readings as the model returns them from different screens; the reader treats them identically.
SCREENS = {
    "smartwatch heart rate": [{"key": "vitals.hr", "value": 72, "confidence": 0.9}],
    "watch blood oxygen": [{"key": "vitals.spo2", "value": 97, "confidence": 0.9}],
    "phone health summary": [{"key": "vitals.hr", "value": 88}, {"key": "vitals.spo2", "value": 95},
                             {"key": "vitals.sbp", "value": 128}, {"key": "vitals.dbp", "value": 82}],
    "glucose app": [{"key": "vitals.glucose", "value": 142}],
    "thermometer app (converted)": [{"key": "vitals.temp", "value": 38.5}],
    "bedside monitor": [{"key": "vitals.hr", "value": 110}, {"key": "vitals.rr", "value": 22}],
}


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_plausible_readings_from_any_screen_are_kept_as_photo_facts(screen):
    facts = VisionReader(ScreenModel(SCREENS[screen])).read(b"jpg", "monitor", photo_id="p1")
    assert {f.key: f.value for f in facts} == {f["key"]: f["value"] for f in SCREENS[screen]}
    assert all(f.role == Role.photo and f.captured_by == CapturedBy.camera for f in facts)
    assert all(f.provenance.photo_id == "p1" for f in facts)


@pytest.mark.parametrize("key", sorted(CFG["plausible_ranges"]))
def test_readings_outside_the_photo_range_are_dropped_for_every_key(key):
    """A misread number (a step count read as a heart rate, a battery % read as SpO2 below the range) never
    becomes a fact, on any screen."""
    lo, hi = CFG["plausible_ranges"][key]
    assert read([{"key": key, "value": hi + 1}]) == {}
    assert read([{"key": key, "value": lo - 1}]) == {}
    assert key in read([{"key": key, "value": (lo + hi) / 2}])


def test_non_numbers_and_an_inverted_pressure_pair_are_dropped():
    assert read([{"key": "vitals.glucose", "value": "HI"}, {"key": "vitals.hr", "value": "--"}]) == {}
    assert read([{"key": "vitals.sbp", "value": 82}, {"key": "vitals.dbp", "value": 128},
                 {"key": "vitals.hr", "value": 88}]) == {"vitals.hr": 88}


def test_a_confident_wearable_reading_still_waits_for_a_tap_and_invented_keys_are_rejected(tmp_path):
    """Consumer-grade readings get no special trust: a photo fact starts unconfirmed however confident the model
    is, and a key the vocabulary does not have (steps from a fitness app) is rejected, not stored."""
    reader = VisionReader(ScreenModel([{"key": "vitals.hr", "value": 118, "confidence": 0.99},
                                       {"key": "activity.steps", "value": 8432, "confidence": 0.99}]))
    c, _ = make_client(vision=reader, vision_model=FakeModel(name="fake-vision"), data_dir=tmp_path)
    r = c.post("/api/photo", files={"file": ("w.jpg", b"\xff\xd8fake", "image/jpeg")}, data={"mode": "monitor"})
    assert r.status_code == 200
    facts = r.json()["facts"]
    assert [(f["key"], f["value"], f["status"]) for f in facts] == [("vitals.hr", 118, "unconfirmed")]
    trace = c.get("/api/state").json()["transcripts"][-1]["trace"]["model"]
    assert [x["key"] for x in trace["rejected"]] == ["activity.steps"]


def test_a_malformed_box_does_not_lose_the_readings():
    """Seen live: the model once wrote a box as a string; the reading is kept, only its crop is dropped."""
    facts = VisionReader(ScreenModel([{"key": "vitals.hr", "value": 88, "box": [0.1, 0.2, 0.3, 0.4]},
                                      {"key": "vitals.sbp", "value": 128, "box": ":[309,441,400,477]},{"},
                                      {"key": "vitals.dbp", "value": 82, "confidence": "high"}])).read(b"jpg", "monitor")
    assert [(f.key, f.value) for f in facts] == [("vitals.hr", 88), ("vitals.sbp", 128), ("vitals.dbp", 82)]
    assert facts[0].provenance.crop == [0.1, 0.2, 0.3, 0.4] and facts[1].provenance.crop is None
