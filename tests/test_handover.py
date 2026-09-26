"""One-tap hand over at the hospital: arrive + transfer + frozen report + end, and the final packet to the ED."""
import asyncio
import io
import json
from datetime import timedelta

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from fakes import make_client
from herald.api.encounters import relay_loop
from herald.core.schema import FactIn, Status


def headers(ctx):
    return {"X-Herald-Patient": ctx.incident.id}


def confirmed(ctx, key, value):
    fact = ctx.incident.ingest(FactIn(key=key, value=value))
    return ctx.incident.set_status(fact.id, Status.confirmed)


def persisted(tmp_path):
    return dict(data_dir=tmp_path / "data", state_key_file=tmp_path / "private" / "key", persistence=True)


class Receiver:
    """An injected relay transport: records every wire packet and acks it, or fails while `down`."""

    def __init__(self):
        self.packets, self.down = [], False

    async def __call__(self, wire: bytes) -> dict:
        if self.down:
            raise ConnectionError("link down")
        packet = json.loads(wire)
        self.packets.append(packet)
        return {"ack": packet["q"]}


def drain(relay, ticks=40):
    async def run():
        for _ in range(ticks):
            await relay.tick()
    asyncio.run(run())


def test_handover_sets_every_timestamp_and_ends_the_call():
    client, ctx = make_client()
    inc = ctx.incident
    arrived = client.post("/api/encounters/current/arrive", headers=headers(ctx)).json()["incident"]["arrived_at"]
    ctx.capture_agent.auto = True
    response = client.post("/api/encounters/current/handover", headers=headers(ctx))
    assert response.status_code == 200
    state = response.json()
    row = state["incident"]
    assert row["arrived_at"] == arrived                    # an earlier arrival is kept
    assert row["transferred_at"] == row["handed_over_at"]  # transfer is recorded at the hand over
    assert row["ended_at"] and row["media_disposal"]       # ended exactly as "finish" does
    assert inc.ended_at >= inc.handed_over_at
    assert not ctx.capture_agent.auto
    assert inc.audit_log[-1] == {"at": row["handed_over_at"], "action": "handover", "actor": "medic", "unconfirmed": 0}
    assert state["relay"]["handover"] == {"at": row["handed_over_at"], "delivered_at": None, "received_at": None}


def test_handover_without_prior_milestones_records_them_at_the_same_moment():
    client, ctx = make_client()
    row = client.post("/api/encounters/current/handover", headers=headers(ctx), json={"destination": None}).json()["incident"]
    assert row["arrived_at"] == row["transferred_at"] == row["handed_over_at"]


def test_second_handover_and_stale_patient_are_refused():
    client, ctx = make_client()
    assert client.post("/api/encounters/current/handover").status_code == 409          # no patient header
    assert client.post("/api/encounters/current/handover", headers=headers(ctx)).status_code == 200
    first = ctx.incident.handed_over_at
    again = client.post("/api/encounters/current/handover", headers=headers(ctx))
    assert again.status_code == 409 and ctx.incident.handed_over_at == first
    assert sum(entry["action"] == "handover" for entry in ctx.incident.audit_log) == 1


def test_frozen_report_equals_the_live_report_and_survives_restore(tmp_path):
    client, ctx = make_client(**persisted(tmp_path))
    confirmed(ctx, "vitals.hr", 116)
    confirmed(ctx, "complaint.chief", "chest pain")
    ctx.incident.ingest(FactIn(key="vitals.sbp", value=173, captured_by="camera"))   # unconfirmed: not in the report
    state = client.post("/api/encounters/current/handover", headers=headers(ctx)).json()
    frozen = ctx.incident.handoff_final
    assert frozen["at"] == state["incident"]["handed_over_at"]
    assert frozen["incident"]["handed_over_at"] == frozen["at"] and frozen["incident"]["ended_at"] is None
    live = client.get("/api/handoff").json()
    assert {k: v for k, v in frozen.items() if k not in ("at", "incident")} == \
           {k: v for k, v in live.items() if k != "incident"}
    assert "116" in frozen["text"] and len(frozen["not_yet_confirmed"]) == 1
    assert ctx.incident.audit_log[-1]["unconfirmed"] == 1

    again, restored = make_client(**persisted(tmp_path))
    assert restored.incident.id == ctx.incident.id
    assert restored.incident.handoff_final == frozen
    assert restored.incident.handed_over_at == ctx.incident.handed_over_at
    assert again.get("/api/state").json()["incident"]["handed_over_at"] == frozen["at"]


def test_final_packet_is_queued_retried_and_marked_delivered_when_acked():
    client, ctx = make_client()
    receiver = Receiver()
    ctx.relay._transport = receiver
    confirmed(ctx, "vitals.hr", 116)
    ctx.incident.ingest(FactIn(key="vitals.sbp", value=173, captured_by="camera"))   # unconfirmed: stays on the vehicle
    state = client.post("/api/encounters/current/handover", headers=headers(ctx),
                        json={"destination": "Valley Medical"}).json()
    assert state["relay"]["authorized"]["destination"] == "Valley Medical"   # authorized by the hand over
    receiver.down = True
    drain(ctx.relay, 6)
    assert ctx.relay.handover_status(ctx.incident)["delivered_at"] is None
    receiver.down = False
    drain(ctx.relay)
    finals = [p for p in receiver.packets if p["tier"] == "handover"]
    assert len(finals) == 1
    final = finals[0]
    assert final["i"] == ctx.incident.id and final["dest"] == "Valley Medical" and final["f"] == {}
    assert final["ho"]["at"] == state["incident"]["handed_over_at"]
    report = ctx.incident.handoff_final
    assert final["ho"]["sections"] == [{"label": s["label"], "lines": [ln["text"] for ln in s["lines"]]}
                                       for s in report["sections"]]
    assert "text" not in final["ho"] and "not_yet_confirmed" not in final["ho"]
    assert "173" not in json.dumps(receiver.packets) and "173" not in report["text"]
    # The latest critical values go first; the final packet follows them.
    assert receiver.packets.index(final) > 0 and receiver.packets[0]["tier"] == "critical"
    status = client.get("/api/state").json()["relay"]["handover"]
    assert status["at"] == final["ho"]["at"] and status["delivered_at"] and status["received_at"] is None
    drain(ctx.relay)
    assert len([p for p in receiver.packets if p["tier"] == "handover"]) == 1   # sent once


def test_handover_authorizes_the_confirmed_destination_and_skips_when_none_is_known():
    client, ctx = make_client()
    ctx.relay._transport = Receiver()
    confirmed(ctx, "transport.destination", "Regional Medical Center")
    client.post("/api/encounters/current/handover", headers=headers(ctx))
    assert ctx.relay.authorized["destination"] == "Regional Medical Center"

    other, octx = make_client()
    octx.relay._transport = Receiver()
    other.post("/api/encounters/current/handover", headers=headers(octx))
    assert octx.relay.authorized is None                     # no destination known: nothing is authorized


def test_received_at_is_the_first_ed_acknowledgement_after_the_handover():
    client, ctx = make_client()
    client.post("/api/encounters/current/handover", headers=headers(ctx))
    at = ctx.incident.handed_over_at
    ctx.relay.clinician_acknowledgements = {ctx.incident.id: [
        {"at": (at - timedelta(minutes=5)).isoformat(), "status": "received", "note": None},   # the pre-alert
        {"at": (at + timedelta(seconds=40)).isoformat(), "status": "received", "note": None},
        {"at": (at + timedelta(minutes=2)).isoformat(), "status": "received", "note": None}]}
    status = client.get("/api/state").json()["relay"]["handover"]
    assert status["received_at"] == (at + timedelta(seconds=40)).isoformat()


def test_capture_is_rejected_after_handover():
    client, ctx = make_client()
    client.post("/api/encounters/current/handover", headers=headers(ctx))
    patient = headers(ctx)
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(1600), 16000, format="WAV", subtype="PCM_16")
    assert client.post("/api/transcript", headers=patient, json={"text": "pulse 90", "use_llm": False}).status_code == 409
    assert client.post("/api/audio", headers=patient,
                       files={"file": ("clip.wav", buffer.getvalue(), "audio/wav")}).status_code == 409
    assert client.post("/api/photo", headers=patient,
                       files={"file": ("photo.jpg", b"image", "image/jpeg")}).status_code == 409
    assert client.post("/api/facts", headers=patient, json=[{"key": "vitals.hr", "value": 90}]).status_code == 409
    assert client.post("/api/capture/auto", json={"on": True, "incident_id": ctx.incident.id}).status_code == 409
    assert client.post("/api/capture/now", json={"incident_id": ctx.incident.id}).status_code == 409
    assert not ctx.incident.facts and not ctx.incident.transcripts


def test_next_patient_after_handover_keeps_the_handed_over_record(tmp_path):
    client, ctx = make_client(**persisted(tmp_path))
    receiver = Receiver()
    ctx.relay._transport = receiver
    confirmed(ctx, "vitals.hr", 116)
    old = ctx.incident
    client.post("/api/encounters/current/handover", headers=headers(ctx), json={"destination": "Valley Medical"})
    frozen = old.handoff_final
    started = client.post("/api/incident", json={"dispatch": None}, headers=headers(ctx))
    assert started.status_code == 200
    state = started.json()
    assert state["incident"]["id"] != old.id and state["incident"]["handed_over_at"] is None
    assert not state["facts"] and state["relay"]["handover"] is None
    row = next(r for r in state["encounter_history"] if r["id"] == old.id)
    assert row["handed_over_at"] == frozen["at"] and row["handover"]["delivered_at"] is None
    # The previous call's own queue still delivers the final packet after the next patient starts, and the delivery
    # is persisted as soon as it is acknowledged.
    async def loop():
        async def changed():
            pass
        try:
            await asyncio.wait_for(relay_loop(ctx, changed), 2.5)
        except asyncio.TimeoutError:
            pass
    asyncio.run(loop())
    assert any(p["tier"] == "handover" and p["i"] == old.id for p in receiver.packets)
    retained = client.get(f"/api/encounters/{old.id}").json()
    assert retained["frozen"] and retained["handoff"] == frozen
    assert retained["handover"]["at"] == frozen["at"] and retained["handover"]["delivered_at"]
    again, restored = make_client(**persisted(tmp_path))
    assert restored.previous_calls[0].roster.incidents()[0].handoff_final == frozen
    assert restored.previous_calls[0].relay.handovers[old.id]["delivered_at"] == retained["handover"]["delivered_at"]


def test_a_new_ed_url_resends_the_final_report():
    client, ctx = make_client()
    receiver = Receiver()
    ctx.relay._transport = receiver
    client.post("/api/encounters/current/handover", headers=headers(ctx), json={"destination": "Valley Medical"})
    drain(ctx.relay)
    assert ctx.relay.handover_status(ctx.incident)["delivered_at"]
    ctx.relay.set_ed_url("http://127.0.0.1:9001")          # a different receiver has not seen the final report
    assert ctx.relay.handover_status(ctx.incident)["delivered_at"] is None
    drain(ctx.relay)
    assert [p["tier"] for p in receiver.packets].count("handover") == 2


def test_current_patient_report_is_frozen_after_handover():
    client, ctx = make_client()
    confirmed(ctx, "vitals.hr", 116)
    client.post("/api/encounters/current/handover", headers=headers(ctx))
    current = client.get(f"/api/encounters/{ctx.incident.id}").json()
    assert current["frozen"] and current["handoff"] == ctx.incident.handoff_final


def test_ed_receiver_stores_the_final_packet_and_the_received_tap():
    from ed_receiver.app import INCIDENTS, LINK, app
    INCIDENTS.clear(); LINK["last_contact_at"] = None
    try:
        ed = TestClient(app)
        client, ctx = make_client()

        async def to_ed(wire: bytes) -> dict:
            return ed.post("/ingest", content=wire, headers={"Content-Type": "application/json"}).json()

        ctx.relay._transport = to_ed
        confirmed(ctx, "vitals.hr", 116)
        client.post("/api/encounters/current/handover", headers=headers(ctx), json={"destination": "Valley Medical"})
        drain(ctx.relay)
        received = ed.get("/state").json()["incidents"][ctx.incident.id]
        handover = received["handover"]
        assert handover["at"] == ctx.incident.handed_over_at.isoformat() and handover["arrived_at"]
        assert handover["sections"] and any("116" in line for s in handover["sections"] for line in s["lines"])
        assert [p["tier"] for p in received["packets"]].count("handover") == 1
        # A retried final packet is acknowledged again but never applied twice.
        again = {"i": ctx.incident.id, "q": handover["seq"], "tier": "handover", "f": {}, "ho": {"at": "changed"}}
        assert ed.post("/ingest", json=again).json()["duplicate"] is True
        assert ed.get("/state").json()["incidents"][ctx.incident.id]["handover"]["at"] == handover["at"]
        ack = ed.post(f"/incidents/{ctx.incident.id}/acknowledgements", json={"status": "received"})
        assert ack.status_code == 200 and ack.json()["at"] >= handover["arrived_at"]
        # The relay reads the ED's acknowledgements back (on its idle probe) and reports the receipt.
        ctx.relay.clinician_acknowledgements = {pid: row.get("acknowledgements", [])
                                                for pid, row in ed.get("/state").json()["incidents"].items()}
        assert client.get("/api/state").json()["relay"]["handover"]["received_at"] == ack.json()["at"]
    finally:
        INCIDENTS.clear(); LINK["last_contact_at"] = None
