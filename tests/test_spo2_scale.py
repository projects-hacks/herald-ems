"""The one-tap NEWS2 SpO2 target switch: POST /api/patient/spo2-scale.

The medic's tap is the clinician direction RCP requires for Scale 2, so the fact is written confirmed in one step and
re-bands SpO2 immediately. Speech can never set it: patient.spo2_scale is require_tap.
"""
from fakes import make_client


def spo2(client):
    return client.get("/api/state").json()["facts"].get("vitals.spo2", {})


def seed(ctx, value=90):
    from herald.core.schema import FactIn
    ctx.incident.ingest(FactIn(key="patient.age", value=72, confidence=0.99))
    ctx.incident.ingest(FactIn(key="vitals.spo2", value=value, confidence=0.99))


def test_one_tap_switches_to_scale_2_and_rebands_spo2():
    client, ctx = make_client()
    seed(ctx, 90)
    assert spo2(client)["severity"] == "critical"                     # Scale 1: 90 is well below 94-98
    r = client.post("/api/patient/spo2-scale", json={"scale": 2})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"   # the tap is the confirmation
    assert "severity" not in spo2(client)                              # Scale 2: 90 is on target


def test_switching_back_restores_scale_1():
    client, ctx = make_client()
    seed(ctx, 90)
    client.post("/api/patient/spo2-scale", json={"scale": 2})
    client.post("/api/patient/spo2-scale", json={"scale": 1})
    state = client.get("/api/state").json()
    assert state["facts"]["patient.spo2_scale"]["value"] == 1
    assert state["facts"]["vitals.spo2"]["severity"] == "critical"


def test_the_switch_is_audited():
    client, ctx = make_client()
    seed(ctx)
    client.post("/api/patient/spo2-scale", json={"scale": 2})
    log = client.get("/api/state").json()["audit"]
    assert any(e.get("key") == "patient.spo2_scale" and e.get("to") == "confirmed" and e.get("actor") == "medic"
               for e in log)


def test_only_scales_1_and_2_are_accepted():
    client, ctx = make_client()
    seed(ctx)
    for bad in (0, 3, -1):
        assert client.post("/api/patient/spo2-scale", json={"scale": bad}).status_code == 400
    assert client.post("/api/patient/spo2-scale", json={"scale": "two"}).status_code == 422


def test_speech_cannot_set_scale_2_on_its_own():
    """The model may extract the key, but it lands unconfirmed and does not re-band: only the tap does."""
    from herald.core.schema import FactIn, Status
    client, ctx = make_client()
    seed(ctx, 90)
    f = ctx.incident.ingest(FactIn(key="patient.spo2_scale", value=2, confidence=0.99))
    assert f.status == Status.unconfirmed
    assert spo2(client)["severity"] == "critical"
