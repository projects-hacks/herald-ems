from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Status


def test_status_changes_are_append_only_audit_events():
    incident = Incident()
    fact = incident.ingest(FactIn(key="triage.category", value="immediate", captured_by=CapturedBy.medic))

    incident.set_status(fact.id, Status.confirmed)
    incident.set_status(fact.id, Status.rejected)

    assert [(event["from"], event["to"], event["key"]) for event in incident.audit_log] == [
        ("unconfirmed", "confirmed", "triage.category"),
        ("confirmed", "rejected", "triage.category"),
    ]
    assert incident.snapshot()["audit"] == incident.audit_log
