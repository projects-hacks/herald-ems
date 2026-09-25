from eval.bench_relay import build_incident, losses, spread
from herald.relay import Relay


def test_benchmark_record_is_confirmed_and_has_critical_values():
    incident = build_incident()
    relay = Relay(lambda: incident)
    assert incident.facts and all(f.status.value == "confirmed" for f in incident.facts)
    assert {"stroke.lkw", "meds.anticoagulant", "vitals.sbp"} <= set(relay.critical_values())


def test_losses_compares_the_ed_state_to_confirmed_values():
    expected = {"vitals.hr": 92, "meds.anticoagulant": "warfarin"}
    state = {"incidents": {"patient": {"fields": {"vitals.hr": {"v": 92}, "meds.anticoagulant": {"v": "other"}}}}}
    assert losses(expected, state, "patient") == 1


def test_spread_reports_three_run_range_for_deck_consumers():
    rows = [
        {"first_critical_ack_ms": 1000, "critical_packet_bytes": 100, "full_sync_bytes": 1000,
         "time_to_reconcile_ms": 1200, "duplicates": 0, "losses": 0},
        {"first_critical_ack_ms": 1100, "critical_packet_bytes": 100, "full_sync_bytes": 1000,
         "time_to_reconcile_ms": 1300, "duplicates": 0, "losses": 0},
        {"first_critical_ack_ms": 1200, "critical_packet_bytes": 100, "full_sync_bytes": 1000,
         "time_to_reconcile_ms": 1400, "duplicates": 0, "losses": 0},
    ]
    summary = spread(rows)
    assert summary["first_critical_ack_ms"] == {"mean": 1100, "min": 1000, "max": 1200, "runs": 3}
    assert summary["losses"]["max"] == 0
