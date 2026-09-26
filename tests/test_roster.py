import pytest

from fakes import make_client
from herald.core.roster import PatientRoster
from herald.core.vocabulary import default_vocabulary


def test_triage_category_uses_the_existing_enum_validation():
    vocabulary = default_vocabulary()
    assert vocabulary.validate("triage.category", "Immediate") == "immediate"
    with pytest.raises(ValueError, match="allowed values"):
        vocabulary.validate("triage.category", "red")


class StubIncident:
    def __init__(self, patient_id, triage=None, summary="", done=0, total=0):
        self.id = patient_id
        self.ended_at = None
        self._triage = triage
        self._snapshot = {"summary": summary, "readiness": ([{"done": done, "total": total}] if total else [])}

    def latest(self, key, confirmed_only=False):
        assert key == "triage.category" and confirmed_only
        return type("Fact", (), {"value": self._triage})() if self._triage else None

    def snapshot(self):
        return self._snapshot


def test_roster_add_activate_and_summaries():
    incidents = iter([
        StubIncident("inc-driver", "immediate", "Driver", 2, 6),
        StubIncident("inc-passenger", "minimal", "Passenger"),
    ])
    roster = PatientRoster(lambda: next(incidents))
    driver = roster.add("Driver")
    passenger = roster.add("Passenger")

    assert roster.active() is passenger
    assert roster.activate(driver.id) is driver
    assert roster.summaries() == [
        {"id": "inc-driver", "label": "Driver", "slot": "Driver", "ended_at": None, "triage": "immediate", "summary": "Driver",
         "readiness_done": 2, "readiness_total": 6},
        {"id": "inc-passenger", "label": "Passenger", "slot": "Passenger", "ended_at": None, "triage": "minimal", "summary": "Passenger",
         "readiness_done": 0, "readiness_total": 0},
    ]


def test_roster_rejects_empty_labels_and_unknown_ids():
    roster = PatientRoster(lambda: StubIncident("inc-1"))
    with pytest.raises(ValueError, match="must not be empty"):
        roster.add("  ")
    with pytest.raises(KeyError):
        roster.activate("missing")


def test_context_incident_property_tracks_active_patient_and_reset_returns_to_one():
    _, context = make_client()
    first = context.incident
    second = context.roster.add("Passenger")
    assert context.incident is second
    context.roster.activate(first.id)
    assert context.incident is first

    replacement = context.new_incident("fall")
    assert context.incident is replacement
    assert len(context.roster.incidents()) == 1


def test_patient_routes_create_activate_and_publish_snapshot_contract():
    client, context = make_client()
    initial = client.get("/api/state").json()
    driver_id = initial["active_patient"]
    assert initial["patients"] == [{
        "id": driver_id, "label": "Patient 1", "slot": "Patient 1", "ended_at": None, "triage": None, "summary": "",
        "readiness_done": 0, "readiness_total": 6,
    }]

    created = client.post("/api/patients", json={"label": " Passenger "})
    assert created.status_code == 200
    passenger_id = created.json()["active_patient"]
    assert passenger_id != driver_id
    assert [row["label"] for row in created.json()["patients"]] == ["Patient 1", "Passenger"]
    assert client.get("/api/patients").json()["active_patient"] == passenger_id
    assert client.post("/api/facts", json=[{
        "key": "vitals.spo2", "value": 98, "captured_by": "device", "role": "device",
        "speaker": "monitor", "confidence": 0.99,
    }]).status_code == 200

    activated = client.post(f"/api/patients/{driver_id}/activate")
    assert activated.status_code == 200 and activated.json()["active_patient"] == driver_id
    assert context.incident.id == driver_id
    assert context.incident.latest("vitals.spo2") is None
    context.roster.activate(passenger_id)
    assert context.incident.latest("vitals.spo2").value == 98
    assert client.post("/api/patients/missing/activate").status_code == 404
    assert client.post("/api/patients", json={"label": " "}).status_code == 422
