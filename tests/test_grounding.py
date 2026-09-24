"""Grounding: a number the model writes must be a number that was said, in digits or in words."""
import pytest

from herald.extraction.grounding import default_grounding

G = default_grounding()


@pytest.mark.parametrize("text,value", [
    ("pressure's now one seventy over ninety eight", 170), ("pressure's now one seventy over ninety eight", 98),
    ("heart rate about a hundred", 100), ("the sugar was one twenty four not one forty two", 124),
    ("BP one oh two over sixty four", 102), ("a hundred and ten", 110), ("72 year old, BP one sixty over ninety", 160),
    ("sats ninety one percent", 91), ("Glucose 142.", 142), ("E4 V4 M6", 6),
])
def test_numbers_said_in_digits_or_words(text, value):
    assert any(abs(v - value) < 0.05 for v in G.numbers_said(text))


def test_decimal_in_words():
    assert 37.1 in G.numbers_said("temp thirty seven point one")


def test_a_number_nobody_said_is_dropped_even_when_the_utterance_has_no_digits():
    """Dev gold v1_088: the model wrote glucose 200 for "reads HI" and RR 20 for "deep and rapid"."""
    t = "Son says she's been vomiting for two days, now she's unresponsive, sugar reads HI, breathing deep and rapid."
    assert not G.supported("vitals.glucose", 200, t) and not G.supported("vitals.rr", 20, t)


def test_spoken_vitals_next_to_other_digits_are_kept():
    t = "72 year old female, BP one sixty over ninety"
    assert G.supported("vitals.sbp", 160, t) and G.supported("vitals.dbp", 90, t)
    assert not G.supported("vitals.hr", 88, t)


def test_derived_values_are_not_held_to_the_rule():
    assert G.supported("vitals.gcs_motor", 6, "obeys commands")
    assert G.supported("vitals.temp", 38.5, "temp 101.3")              # converted from Fahrenheit


def test_thousands_and_unknown_source_and_rating_words():
    assert 4000 in G.numbers_said("heparin four thousand units") and 1500 in G.numbers_said("one thousand five hundred")
    assert G.supported("meds.given", {"drug": "heparin", "dose": 4000.0}, "heparin four thousand units IV")
    assert G.supported("infection.suspected", "unknown", "looks septic, no clear source")
    assert not G.supported("complaint.chief", "unknown", "unknown")
    assert G.supported("vitals.pain", 8, "patient's still rating it an eight")
