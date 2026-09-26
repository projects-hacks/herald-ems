"""The patient is called by the confirmed name everywhere (roster, ED packets, history), and events merged "each"
(drugs given, procedures) never read as a change of the one before (live demo run, 2026-09-26)."""
from fakes import make_client
from herald.core.schema import CapturedBy, FactIn, Role


def test_the_confirmed_name_becomes_the_label_and_a_reported_one_does_not():
    client, ctx = make_client()
    inc = ctx.incident
    reported = inc.ingest(FactIn(key="patient.name", value="Robert Chen", role=Role.unknown, captured_by=CapturedBy.other))
    assert inc.display_label == inc.patient_label                       # heard, not confirmed: still the slot
    client.post(f"/api/facts/{reported.id}/confirm")
    assert inc.display_label == "Robert Chen"
    row = client.get("/api/state").json()["patients"][0]
    assert row["label"] == "Robert Chen" and row["slot"] == inc.patient_label


def test_a_drug_given_after_another_is_not_a_change_of_it():
    client, ctx = make_client()
    inc = ctx.incident
    inc.ingest(FactIn(key="meds.given", value={"drug": "epinephrine", "dose": 1, "unit": "mg", "route": "IV", "by": "crew"}))
    second = inc.ingest(FactIn(key="meds.given", value={"drug": "sodium chloride", "dose": 500, "unit": "mL", "route": "IV", "by": "crew"}))
    assert second.previous_value is None and second.previous_ts is None
    inc.ingest(FactIn(key="vitals.hr", value=96))
    assert inc.ingest(FactIn(key="vitals.hr", value=110)).previous_value == 96   # a measure still shows "was"
