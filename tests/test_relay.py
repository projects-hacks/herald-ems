"""Relay guarantees: only confirmed facts leave, critical first, and after any pattern of
failures the ED ends with exactly the rig's critical values: 0 duplicates applied, 0 lost."""
import asyncio
import json
import random

from eval.baselines.rules_extractor import extract  # test input generator only
from herald.relay import Relay
from herald.relay.relay import _kept_local_pct
from herald.core.schema import CapturedBy, FactIn, Role, Status
from herald.core.incident import Incident


class FakeED:
    def __init__(self, fail_rate=0.0, seed=0):
        self.fields, self.applied, self.duplicates, self.bytes = {}, [], 0, []
        self.withdrawals = []
        self.fields_by_patient = {}
        self.patient_order = []
        self.rng = random.Random(seed)
        self.fail_rate = fail_rate

    async def __call__(self, wire: bytes) -> dict:
        p = json.loads(wire)
        lost_request = self.rng.random() < self.fail_rate / 2
        if lost_request:
            raise ConnectionError("request lost")
        duplicate = p["q"] in self.applied
        if duplicate:
            self.duplicates += 1
        else:
            self.fields.update(p["f"])
            for key in p.get("rm", []):
                self.fields.pop(key, None)
                self.withdrawals.append(key)
            patient_fields = self.fields_by_patient.setdefault(p["i"], {})
            patient_fields.update(p["f"])
            for key in p.get("rm", []):
                patient_fields.pop(key, None)
            self.patient_order.append(p["i"])
            self.applied.append(p["q"])
            self.bytes.append(len(wire))
        if self.rng.random() < self.fail_rate / 2:   # applied, but the ACK is lost -> sender retries
            raise ConnectionError("ack lost")
        return {"ack": p["q"], "duplicate": duplicate} if duplicate else {"ack": p["q"]}


def build_incident():
    inc = Incident(dispatch="possible stroke")
    for t in ["68-year-old female, sudden left-sided weakness, husband says she was fine at 1:40.",
              "Mild left facial droop, left arm and leg can't lift, eyes deviated to the right, no agnosia.",
              "Onset was witnessed. BP 182 over 104, pulse 92, SpO2 95 on room air, respirations 18, temp 37.1, alert.",
              "She takes warfarin. Glucose 142. Transporting to Valley Medical, ETA 12 minutes."]:
        for f in extract(t):
            inc.ingest(f, record=False)
    inc.commit()
    return inc


def build_triage_incident(label, triage, complaint):
    inc = Incident(dispatch="multi-vehicle collision")
    inc.patient_label = label
    for key, value in [("triage.category", triage), ("complaint.chief", complaint)]:
        fact = inc.ingest(FactIn(key=key, value=value, captured_by=CapturedBy.medic, confidence=0.99),
                          record=False)
        inc.set_status(fact.id, Status.confirmed)
    inc.commit()
    return inc


async def drain(relay, max_ticks=400):
    for _ in range(max_ticks):
        await relay.tick()
        if not relay.pending() and relay.inflight is None:
            return


def test_nothing_sent_without_authorization():
    inc = build_incident()
    ed = FakeED()
    r = Relay(lambda: inc, transport=ed)
    asyncio.run(drain(r, 5))
    assert ed.applied == []


def test_reconciles_exactly_over_a_flaky_link():
    for seed in range(20):
        inc = build_incident()
        ed = FakeED(fail_rate=0.5, seed=seed)
        r = Relay(lambda: inc, transport=ed)
        r.authorize("Valley Medical")
        asyncio.run(drain(r))
        crit = r.critical_values()
        assert {k: ed.fields.get(k) for k in crit} == crit, f"seed {seed}: lost or stale fields"
        assert len(ed.applied) == len(set(ed.applied))       # no packet applied twice
        assert r.duplicates_acked == ed.duplicates, f"seed {seed}: relay's own count disagrees with the ED's"


def test_reconciliation_counter_reflects_a_real_retry_not_a_guess():
    """P3.2: the 'N duplicates' shown after a restore is the ED's own count of resent sequence numbers it
    already had, not a client-side estimate. An ack that gets lost after the ED applied the packet forces
    exactly one retry, which the ED reports back as a duplicate; nothing here is inferred from a sequence gap.
    A dispatch that opens no checklist keeps the incident's only pending field at one (no synthetic
    "alert.readiness" riding along), so a failed send does not also drop the in-flight packet for being
    oversized on a now-degraded link (relay.py's own weak-link shed rule)."""
    inc = Incident(dispatch="abdominal pain")
    fact = inc.ingest(FactIn(key="vitals.hr", value=92, captured_by=CapturedBy.medic, confidence=0.99), record=False)
    inc.set_status(fact.id, Status.confirmed)
    inc.commit()
    ed = FakeED()
    ack_lost_once = {"done": False}

    async def flaky_once(wire: bytes) -> dict:
        result = await ed(wire)
        if not ack_lost_once["done"]:
            ack_lost_once["done"] = True
            raise ConnectionError("ack lost")   # the ED applied it; the client never saw the ack
        return result

    r = Relay(lambda: inc, transport=flaky_once)
    r.authorize("Valley Medical")
    assert r.status()["duplicates_acked"] == 0
    asyncio.run(r.tick())   # applied at the ED, but the client times out and keeps the packet in flight
    assert r.duplicates_acked == 0 and r.inflight is not None
    asyncio.run(r.tick())   # retry: same sequence number, the ED reports it back as a duplicate
    assert r.duplicates_acked == 1 == ed.duplicates
    assert r.status()["duplicates_acked"] == 1


def test_unconfirmed_facts_never_leave():
    inc = build_incident()
    for f in extract("Mom is allergic to aspirin.", captured_by=CapturedBy.other,
                     default_role=Role.family, default_speaker="daughter"):
        inc.ingest(f)
    ed = FakeED()
    r = Relay(lambda: inc, transport=ed)
    r.authorize("Valley Medical")
    asyncio.run(drain(r))
    assert ed.fields.get("allergies") in (None, [])          # the unconfirmed claim was not sent


def test_weak_link_sends_critical_first_in_small_packets():
    inc = build_incident()
    ed = FakeED()
    r = Relay(lambda: inc, transport=ed)
    r.authorize("Valley Medical")
    r.results.extend([(False, 3000), (True, 1500)])          # measured weak link
    asyncio.run(r.tick())
    first = json.loads(json.dumps(ed.fields))
    assert "meds.anticoagulant" in first and "stroke.lkw" in first
    assert "patient.age" not in first                          # demographics wait
    assert ed.bytes[0] <= 420


def test_rejected_critical_fact_is_withdrawn_from_the_ed_with_an_audit_event():
    inc = build_incident()
    ed = FakeED()
    relay = Relay(lambda: inc, transport=ed)
    relay.authorize("Valley Medical")
    asyncio.run(drain(relay))
    assert ed.fields["meds.anticoagulant"] == "warfarin"

    fact = inc.latest("meds.anticoagulant", confirmed_only=True)
    inc.set_status(fact.id, Status.rejected)
    asyncio.run(drain(relay))

    assert "meds.anticoagulant" not in ed.fields
    assert ed.withdrawals == ["meds.anticoagulant"]
    assert relay.log[-1]["removed"] == ["meds.anticoagulant"]


def test_weak_link_prioritizes_immediate_patient_before_minimal_patient():
    minimal = build_triage_incident("Passenger", "minimal", "arm pain")
    immediate = build_triage_incident("Driver", "immediate", "difficulty breathing")
    ed = FakeED()
    relay = Relay(lambda: [minimal, immediate], transport=ed)
    relay.authorize("Valley Medical")
    relay.results.extend([(False, 3000), (True, 1500)])

    asyncio.run(relay.tick())

    assert ed.patient_order == [immediate.id]
    assert {"triage.category", "complaint.chief"} <= set(ed.fields_by_patient[immediate.id])
    assert relay.pending()[0][5] is minimal


def test_unknown_triage_uses_configured_unknown_rank():
    unknown = build_incident()
    immediate = build_triage_incident("Driver", "immediate", "difficulty breathing")
    relay = Relay(lambda: [unknown, immediate])

    rows = relay.pending()

    assert rows[0][5] is immediate
    unknown_rows = [row for row in rows if row[5] is unknown]
    assert unknown_rows and {row[0] for row in unknown_rows} == {relay.tiers.triage_rank["unknown"]}


def test_two_patients_reconcile_without_duplicates_or_loss_on_flaky_link():
    for seed in range(20):
        minimal = build_triage_incident("Passenger", "minimal", "arm pain")
        immediate = build_triage_incident("Driver", "immediate", "difficulty breathing")
        ed = FakeED(fail_rate=0.5, seed=seed)
        relay = Relay(lambda: [minimal, immediate], transport=ed)
        relay.authorize("Valley Medical")

        asyncio.run(drain(relay))

        for incident in (minimal, immediate):
            assert ed.fields_by_patient[incident.id] == relay.critical_values(incident), f"seed {seed}"
        assert len(ed.applied) == len(set(ed.applied))


def test_recorded_stroke_replay_kept_local_percentage_is_clamped():
    assert _kept_local_pct(bytes_sent=25837, bytes_without_relay=16403) == 0.0
    assert _kept_local_pct(bytes_sent=4100, bytes_without_relay=16400) == 75.0


def test_local_bytes_are_counted_per_incident_not_just_as_one_pooled_total(tmp_path):
    """E3: the "kept local" story has to survive a mass-casualty incident with several open patients, so
    `status()` breaks bytes down per patient instead of only reporting one number across all of them."""
    small = build_triage_incident("Passenger", "minimal", "arm pain")
    big = build_triage_incident("Driver", "immediate", "difficulty breathing")
    for i in range(20):
        fact = big.ingest(FactIn(key="scene.notes", value=f"note {i}" * 10, captured_by=CapturedBy.medic,
                                 confidence=0.99), record=False)
        big.set_status(fact.id, Status.confirmed)
    big.commit()
    audio_id = "a_test_clip"
    small.register_media("audio", audio_id)
    (tmp_path / f"{audio_id}.wav").write_bytes(b"x" * 4096)

    relay = Relay(lambda: [small, big], audio_dir=tmp_path)
    status = relay.status()

    assert status["patients"][small.id]["local_bytes"] > 4096          # its own facts, plus its own 4 KiB clip
    assert status["patients"][big.id]["local_bytes"] > status["patients"][small.id]["local_bytes"] - 4096
    assert status["local_bytes"] == sum(row["local_bytes"] for row in status["patients"].values())
    # `big`'s clip never existed, so none of its byte count comes from `small`'s audio file.
    assert status["patients"][big.id]["local_bytes"] < status["local_bytes"]
