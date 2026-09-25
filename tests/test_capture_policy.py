from herald.capture.config import capture_config
from herald.capture.policy import CapturePolicy
from herald.capture.types import IncidentEvent
from herald.core.incident import Incident
from herald.core.schema import FactIn


def event(key, value, kind="facts_added", **kw):
    fact = Incident().ingest(FactIn(key=key, value=value))
    return IncidentEvent(kind, [fact], **kw)


def test_all_configured_fact_triggers_and_family_exception():
    policy = CapturePolicy(capture_config())
    for key, value, mode, purpose in [
        ("meds.given", {"drug": "naloxone", "by": "crew"}, "pill_bottle", "verify"),
        ("meds.list", ["warfarin"], "pill_bottle", "record"),
        ("meds.anticoagulant", "warfarin", "pill_bottle", "record"),
        ("code_status", "DNR", "form", "record"),
    ]:
        intent, = policy.on_event(event(key, value))
        assert (intent.mode, intent.purpose) == (mode, purpose)
    assert policy.on_event(event("meds.given", {"drug": "naloxone", "by": "family"})) == []


def test_eta_once_and_alerts_and_suppression():
    policy = CapturePolicy(capture_config())
    assert policy.on_event(IncidentEvent("eta_changed", [], {"eta_min": 6})) == []
    assert len(policy.on_event(IncidentEvent("eta_changed", [], {"eta_min": 5}))) == 1
    assert policy.on_event(IncidentEvent("eta_changed", [], {"eta_min": 3})) == []
    states = frozenset(["cpr_in_progress"])
    assert len(policy.on_event(IncidentEvent("alert_new", [], states=states))) == 1
    assert policy.on_event(event("code_status", "DNR", states=states)) == []
    policy.reset()
    assert policy.on_event(IncidentEvent("eta_changed", [], {"eta_min": 5}))


def test_monitor_requires_roi_stability_and_refreshes():
    policy = CapturePolicy(capture_config())
    assert policy.on_tick(0, {"usable": True, "changed": True}) == []
    state = dict(roi=True, usable=True, stable=True, changed=True)
    assert policy.on_tick(1, state) == []
    intent, = policy.on_tick(2, state)
    policy.captured(intent, 2)
    assert policy.on_tick(3, state) == []
    state["changed"] = False
    assert policy.on_tick(30, state) == []
    assert policy.on_tick(62, state)[0].trigger == "monitor_refresh"
