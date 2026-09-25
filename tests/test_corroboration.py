"""Batch confirm: one monitor frame confirms as one reading, and a reading that
jumps past its plausible step is flagged for individual review instead of being auto-confirmed or swept in."""
from fakes import tiny_normalizer
from herald.core.corroboration import CorroborationRules, default_corroboration
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Provenance, Status
from herald.core.vocabulary import default_vocabulary
from test_capture_agent import run_frame, setup


def camera_fact(inc, key, value, frame_id):
    return inc.ingest(FactIn(key=key, value=value, captured_by=CapturedBy.camera,
                             provenance=Provenance(frame_id=frame_id, trigger="monitor_changed")))


def test_corroboration_config_matches_the_vocabulary():
    assert CorroborationRules.from_config().problems(default_vocabulary()) == []


def test_first_monitor_reading_batches_as_one_group():
    vocab = default_vocabulary()
    inc = Incident(vocabulary=vocab)
    hr = camera_fact(inc, "vitals.hr", 88, "frame1")
    sbp = camera_fact(inc, "vitals.sbp", 140, "frame1")
    groups = default_corroboration(vocab).groups(inc)
    assert len(groups) == 1
    g = groups[0]
    assert g["frame_id"] == "frame1"
    assert set(g["batch_fact_ids"]) == {hr.id, sbp.id}
    assert g["individual"] == []


def test_jump_beyond_plausible_step_is_flagged_not_batched_or_auto_confirmed():
    vocab = default_vocabulary()
    inc = Incident(vocabulary=vocab)
    camera_fact(inc, "vitals.sbp", 140, "frame1")
    hr2 = camera_fact(inc, "vitals.hr", 90, "frame2")
    sbp2 = camera_fact(inc, "vitals.sbp", 190, "frame2")   # +50 mmHg, past max_step 20
    g = next(g for g in default_corroboration(vocab).groups(inc) if g["frame_id"] == "frame2")
    assert g["batch_fact_ids"] == [hr2.id]
    assert [row["id"] for row in g["individual"]] == [sbp2.id]
    assert sbp2.status == Status.unconfirmed    # flagged, never auto-confirmed
    assert "moved" in g["individual"][0]["reason"]


def test_meds_allergies_code_status_never_batch_even_as_a_first_camera_reading():
    vocab = default_vocabulary()
    inc = Incident(vocabulary=vocab)
    dose = camera_fact(inc, "meds.given", {"drug": "naloxone", "dose": .4, "unit": "mg", "by": "crew"}, "frame1")
    code = camera_fact(inc, "code_status", "DNR", "frame1")
    g = default_corroboration(vocab).groups(inc)[0]
    assert g["batch_fact_ids"] == []
    assert {row["id"] for row in g["individual"]} == {dose.id, code.id}


def test_readings_confirm_endpoint_batches_one_monitor_frame_in_one_tap(tmp_path):
    facts = [FactIn(key="vitals.hr", value=88), FactIn(key="vitals.sbp", value=140),
             FactIn(key="vitals.spo2", value=97), FactIn(key="vitals.rr", value=16)]
    client, ctx = setup(tmp_path, facts)
    client.post("/api/capture/auto", json={"on": True})
    client.post("/api/capture/roi", json={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    run_frame(client, ctx, monitor=True)

    state = client.get("/api/state").json()
    groups = state["capture_groups"]
    assert len(groups) == 1
    group = groups[0]
    assert len(group["batch_fact_ids"]) == 4 and group["individual"] == []
    keys = ["vitals.hr", "vitals.sbp", "vitals.spo2", "vitals.rr"]
    assert all(state["facts"][k]["status"] == "unconfirmed" for k in keys)

    r = client.post(f"/api/readings/{group['frame_id']}/confirm")
    assert r.status_code == 200
    body = r.json()
    assert set(body["confirmed"]) == set(group["batch_fact_ids"]) and body["individual"] == []

    state2 = client.get("/api/state").json()
    assert all(state2["facts"][k]["status"] == "confirmed" for k in keys)
    assert state2["capture_groups"] == []   # nothing left unconfirmed for this frame
    assert client.post(f"/api/readings/{group['frame_id']}/confirm").status_code == 404
    assert client.post("/api/readings/never-existed/confirm").status_code == 404


def test_readings_confirm_leaves_a_jump_unconfirmed_but_batches_the_rest(tmp_path):
    vision_facts = [FactIn(key="vitals.hr", value=88), FactIn(key="vitals.sbp", value=140)]
    client, ctx = setup(tmp_path, vision_facts)
    client.post("/api/capture/auto", json={"on": True})
    client.post("/api/capture/roi", json={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    run_frame(client, ctx, monitor=True, manual=True)
    baseline = client.get("/api/state").json()["capture_groups"][0]["frame_id"]
    client.post(f"/api/readings/{baseline}/confirm")

    ctx.capture_agent.last_input = float("-inf")
    ctx.frame_reader.vision.facts = [FactIn(key="vitals.hr", value=92), FactIn(key="vitals.sbp", value=190)]
    run_frame(client, ctx, monitor=True, manual=True)

    state = client.get("/api/state").json()
    groups = state["capture_groups"]
    assert len(groups) == 1
    g = groups[0]
    hr_id, sbp_id = state["facts"]["vitals.hr"]["id"], state["facts"]["vitals.sbp"]["id"]
    assert g["batch_fact_ids"] == [hr_id]
    assert [row["id"] for row in g["individual"]] == [sbp_id]

    r = client.post(f"/api/readings/{g['frame_id']}/confirm")
    body = r.json()
    assert body["confirmed"] == [hr_id]
    assert body["individual"][0]["id"] == sbp_id

    state2 = client.get("/api/state").json()
    assert state2["facts"]["vitals.hr"]["status"] == "confirmed"
    assert state2["facts"]["vitals.sbp"]["status"] == "unconfirmed"
