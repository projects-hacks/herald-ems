"""The display-only monitor fixture stays explicit about its synthetic boundaries."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monitor_fixture_is_a_complete_synthetic_transport_journey():
    fixture = json.loads((ROOT / "ui/public/fixtures/monitor_journey.json").read_text())

    assert "not a physiological model" in fixture["description"]
    assert fixture["scenario_label"] == "Synthetic post-ROSC transport after a cardiac arrest"
    assert [step["minute"] for step in fixture["steps"]] == [10, 14, 18, 22, 26, 30]
    assert fixture["simulated_minutes"] == {"start": 10, "end": 30}
    assert fixture["display"]["tick_ms"] == 1000
    simulated_minutes_per_tick = fixture["display"]["simulated_minutes_per_tick"]
    expected_samples = round((30 - 10) / simulated_minutes_per_tick) + 1
    assert expected_samples == 121

    keys = [reading["key"] for reading in fixture["readings"]]
    assert keys == ["vitals.hr", "vitals.sbp", "vitals.dbp", "vitals.spo2", "vitals.rr", "vitals.etco2", "vitals.temp"]
    assert all(set(keys).issubset(step) for step in fixture["steps"])


def test_every_listed_scenario_is_a_complete_journey_the_jump_check_accepts():
    # The simulator's picker (ui/public/monitor.js) lists these; each plays at the same pace, over the same keys, and a
    # change between two camera reads 30 s apart stays inside the capture agent's jump limits (config/capture.yaml), so
    # the demo's own values are never held as misreads.
    import yaml
    listing = json.loads((ROOT / "ui/public/fixtures/monitor_scenarios.json").read_text())
    ids = [s["id"] for s in listing["scenarios"]]
    assert listing["default"] in ids and len(ids) == len(set(ids)) >= 4
    limits = yaml.safe_load((ROOT / "config/capture.yaml").read_text())["monitor"]["jump"]["max_step"]
    for s in listing["scenarios"]:
        fixture = json.loads((ROOT / "ui/public" / s["file"].lstrip("/")).read_text())
        assert "not a physiological model" in fixture["description"] and fixture["scenario_label"]
        assert fixture["display"] == {"tick_ms": 1000, "simulated_minutes_per_tick": 0.1666666667}
        assert [step["minute"] for step in fixture["steps"]] == [10, 14, 18, 22, 26, 30]
        keys = [reading["key"] for reading in fixture["readings"]]
        assert keys == ["vitals.hr", "vitals.sbp", "vitals.dbp", "vitals.spo2", "vitals.rr", "vitals.etco2", "vitals.temp"]
        assert fixture["rhythm"]["type"] in {"sinus", "stemi", "af"} and fixture["rhythm"]["label"]
        per_minute = {k: max(abs(b[k] - a[k]) / (b["minute"] - a["minute"]) for a, b in zip(fixture["steps"], fixture["steps"][1:]))
                      for k in keys}
        # 30 s of real time is 5 simulated minutes at one tick (1/6 minute) per second
        assert all(per_minute[k] * 5 < limits[k] for k in keys), (s["id"], per_minute)
