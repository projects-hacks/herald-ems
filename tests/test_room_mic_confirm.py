"""Room-mic facts (owner's decision, 2026-09-26): the crew is hands-free on one microphone, so a fact heard there
confirms itself when the check step kept it and the model is sure -- except who the patient is, allergies,
medications, what was given and code status, which always wait for a tap."""
from herald.core.confirmation import ConfirmationPolicy
from herald.core.schema import CapturedBy, FactIn, Provenance, Role, Status
from herald.core.vocabulary import default_vocabulary
from herald.extraction.verify import FactVerifier

POLICY = ConfirmationPolicy(default_vocabulary(), 0.8, room_mic=(True, frozenset({"allergies", "meds.given", "patient.name"})))


def heard(key, value, *, checked=True, confidence=0.95, hold=None, role=Role.unknown, by=CapturedBy.other):
    return FactIn(key=key, value=value, role=role, captured_by=by, confidence=confidence,
                  provenance=Provenance(checked=checked, hold_reason=hold))


def status(fin):
    return POLICY.initial_status(fin, None, fin.value)


def test_a_checked_confident_room_mic_fact_confirms_itself():
    assert status(heard("vitals.hr", 96)) == Status.confirmed


def test_the_safety_keys_always_wait_for_a_tap():
    assert status(heard("allergies", ["penicillin"])) == Status.unconfirmed
    assert status(heard("meds.given", {"drug": "aspirin"})) == Status.unconfirmed
    assert status(heard("patient.name", "Robert Chen")) == Status.unconfirmed


def test_unchecked_unsure_held_or_attributed_facts_still_wait():
    assert status(heard("vitals.hr", 96, checked=False)) == Status.unconfirmed        # the check step didn't answer
    assert status(heard("vitals.hr", 96, confidence=0.5)) == Status.unconfirmed       # the model wasn't sure
    assert status(heard("vitals.hr", 96, hold="said with a command")) == Status.unconfirmed
    assert status(heard("vitals.hr", 96, role=Role.family)) == Status.unconfirmed     # a named other speaker
    assert status(heard("vitals.hr", 96, by=CapturedBy.camera)) == Status.unconfirmed


def test_off_by_config_keeps_every_room_mic_fact_for_a_tap():
    off = ConfirmationPolicy(default_vocabulary(), 0.8, room_mic=(False, frozenset()))
    assert off.initial_status(heard("vitals.hr", 96), None, 96) == Status.unconfirmed


def test_only_an_explicit_keep_marks_a_fact_checked():
    class Judge:
        def chat_json(self, *a, **k):
            return {"facts": [{"n": 1, "keep": True, "why": "said"}]}      # fact 2 left unanswered
    facts = [FactIn(key="vitals.hr", value=96), FactIn(key="vitals.rr", value=18)]
    kept, _ = FactVerifier(Judge()).check("heart rate ninety six, resps eighteen", facts)
    assert [f.provenance.checked for f in kept] == [True, False]
