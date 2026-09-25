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
        if p["q"] in self.applied:
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


def build_multi_tier_incident():
    """One confirmed fact from each relay tier (config/relay.yaml), a stroke checklist and a trauma mechanism
    both present, so a scope's tier ceiling and its cross-alert reach can both be exercised."""
    inc = Incident(dispatch="possible stroke")
    facts = [("stroke.lkw", "2026-09-25T10:00:00"),      # tier 1
             ("score.race", None),                        # tier 2 is score-derived, not a plain fact; skipped here
             ("vitals.sbp", 150),                          # tier 3
             ("transport.eta_min", 12),                    # tier 4
             ("patient.age", 68)]                          # tier 5
    for key, value in facts:
        if value is None:
            continue
        f = inc.ingest(FactIn(key=key, value=value, captured_by=CapturedBy.medic, confidence=0.99), record=False)
        inc.set_status(f.id, Status.confirmed)
    inc.commit()
    return inc


def test_authorized_scope_restricts_relay_to_its_tier_ceiling():
    """B5: pending()/critical_values() must honour the scope the medic actually authorized, not send every tier
    regardless of it (config/relay.yaml `scopes`, herald/relay/tiers.py `RelayScopes`)."""
    inc = build_multi_tier_incident()
    r = Relay(lambda: inc)

    r.authorize("Valley Medical", "Stroke alert pre-alert set", ("stroke",))
    scoped = r.critical_values(inc)
    assert "stroke.lkw" in scoped and "vitals.sbp" in scoped          # tiers 1 and 3: in a stroke pre-alert's ceiling
    assert "transport.eta_min" not in scoped and "patient.age" not in scoped  # tiers 4-5: not part of that consent
    assert {k for _, _, _, k, _, _ in r.pending()} == set(scoped)

    r.authorize("Valley Medical", "patient update set", ())
    full = r.critical_values(inc)
    assert "transport.eta_min" in full and "patient.age" in full      # no specific alert open: unrestricted again


def test_relay_scopes_union_ceilings_across_simultaneously_open_alerts():
    from herald.relay.tiers import RelayScopes, default_tiers
    scopes = RelayScopes.from_config()
    tiers = default_tiers()
    stroke_only = scopes.allowed_keys(("stroke",), tiers)
    trauma_only = scopes.allowed_keys(("trauma",), tiers)
    both = scopes.allowed_keys(("stroke", "trauma"), tiers)
    assert stroke_only == trauma_only            # both pre-alert scopes share the same tier-1-3 ceiling today
    assert both == stroke_only                   # union of equal ceilings changes nothing, but must not shrink it
    assert scopes.allowed_keys((), tiers) == scopes.allowed_keys(("not-a-real-alert",), tiers)  # falls back to default_scope
