"""Relay guarantees: only confirmed facts leave, critical first, and after any pattern of
failures the ED ends with exactly the rig's critical values: 0 duplicates applied, 0 lost."""
import asyncio
import json
import random

from eval.baselines.rules_extractor import extract  # test input generator only
from herald.relay import Relay
from herald.core.schema import CapturedBy, Role, Status
from herald.core.incident import Incident


class FakeED:
    def __init__(self, fail_rate=0.0, seed=0):
        self.fields, self.applied, self.duplicates, self.bytes = {}, [], 0, []
        self.withdrawals = []
        self.rng = random.Random(seed)
        self.fail_rate = fail_rate

    async def __call__(self, wire: bytes) -> dict:
        p = json.loads(wire)
        lost_request = self.rng.random() < self.fail_rate / 2
        if lost_request:
            raise ConnectionError("request lost")
        if p["q"] in self.applied:
            self.duplicates += 1
        else:
            self.fields.update(p["f"])
            for key in p.get("rm", []):
                self.fields.pop(key, None)
                self.withdrawals.append(key)
            self.applied.append(p["q"])
            self.bytes.append(len(wire))
        if self.rng.random() < self.fail_rate / 2:   # applied, but the ACK is lost -> sender retries
            raise ConnectionError("ack lost")
        return {"ack": p["q"]}


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
