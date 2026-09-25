"""The display-only monitor fixture stays explicit about its synthetic boundaries."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monitor_fixture_is_a_complete_synthetic_transport_journey():
    fixture = json.loads((ROOT / "ui/public/fixtures/monitor_journey.json").read_text())

    assert "not a physiological model" in fixture["description"]
    assert fixture["scenario_label"] == "Synthetic post-ROSC deterioration during stroke transport"
    assert [step["minute"] for step in fixture["steps"]] == [10, 14, 18, 22, 26, 30]
    assert fixture["simulated_minutes"] == {"start": 10, "end": 30}

    keys = [reading["key"] for reading in fixture["readings"]]
    assert keys == ["vitals.hr", "vitals.sbp", "vitals.spo2", "vitals.rr", "vitals.etco2"]
    assert all(set(keys).issubset(step) for step in fixture["steps"])
