"""Structured events (a medication given, a procedure done): one fact per event, fields validated and grounded."""
from herald.core.incident import Incident
from herald.core.schema import CapturedBy, FactIn, Role
from herald.core.vocabulary import default_vocabulary
from herald.extraction.grounding import default_grounding

V = default_vocabulary()
G = default_grounding()


def test_record_fields_are_coerced_and_unknown_fields_dropped():
    v = V.validate("meds.given", {"drug": "aspirin", "dose": "324", "unit": "mg", "route": "PO", "junk": 1})
    assert v == {"drug": "aspirin", "dose": 324.0, "unit": "mg", "route": "PO"}
    assert V.validate("meds.given", "naloxone") == {"drug": "naloxone"}


def test_record_needs_its_identity_and_plausible_numbers():
    for bad in ({"dose": 4}, {"drug": "aspirin", "dose": 99999}):
        try:
            V.validate("meds.given", bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_a_dose_must_be_a_number_that_was_said():
    t = "gave three twenty four of aspirin chewed"
    assert G.supported("meds.given", {"drug": "aspirin", "dose": 324.0}, t)
    assert not G.supported("meds.given", {"drug": "aspirin", "dose": 81.0}, t)


def test_pain_zero_is_a_real_value():
    assert G.supported("vitals.pain", 0, "pain is zero out of ten now")
    assert not G.supported("vitals.hr", 0, "heart rate zero")


def test_each_administration_is_its_own_event_and_repeats_are_kept_apart():
    inc = Incident()
    for v in ({"drug": "naloxone", "dose": 2, "unit": "mg", "time": "14:05"},
              {"drug": "naloxone", "dose": 2, "unit": "mg", "time": "14:09"},
              {"drug": "naloxone", "dose": 2, "unit": "mg", "time": "14:09"}):     # the same dose said twice
        inc.ingest(FactIn(key="meds.given", value=v, role=Role.medic, captured_by=CapturedBy.medic, confidence=0.99))
    assert [x["time"] for x in inc.values()["meds.given"]] == ["14:05", "14:09"]


def test_small_doses_keep_their_precision():
    """Pediatric epinephrine 0.15 mg must not be rounded to 0.1 (found writing gold v3)."""
    assert V.validate("meds.given", {"drug": "epinephrine", "dose": 0.15, "unit": "mg"})["dose"] == 0.15
    assert V.validate("meds.given", {"drug": "fentanyl", "dose": "0.05"})["dose"] == 0.05
    assert V.validate("vitals.temp", 38.46) == 38.5                    # vitals keep one decimal


def test_who_gave_it_is_a_category():
    assert V.validate("meds.given", {"drug": "epinephrine", "by": "Husband"})["by"] == "family"
    assert V.validate("meds.given", {"drug": "naloxone", "by": "Engine"})["by"] == "fire"
    assert V.validate("procedures.done", {"procedure": "cpr", "by": "coworker"})["by"] == "bystander"
    assert V.validate("meds.given", {"drug": "aspirin", "by": "crew"})["by"] == "crew"
