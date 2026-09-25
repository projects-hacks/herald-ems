"""Spanish number words (config/numbers.yaml) for the grounding check: a correct fact from Spanish speech must not be
dropped as unsaid, and the English readings stay exactly as they were (LABELING_GUIDE §5f, MODEL_PLAN §0k)."""
import pytest

from herald.config import load_yaml
from herald.extraction.grounding import Grounding, default_grounding
from herald.extraction.numbers import SpokenNumberLanguages, SpokenNumbers, fold_accents

G = default_grounding()
ES = SpokenNumbers.from_config(load_yaml("numbers.yaml")["es"])


@pytest.mark.parametrize("text,value", [
    ("la presión está en ciento ochenta sobre cien", 180), ("la presión está en ciento ochenta sobre cien", 100),
    ("noventa y dos", 92), ("tiene setenta y ocho años", 78), ("el azúcar le salió en cuarenta y dos", 42),
    ("dieciséis respiraciones", 16), ("dieciseis", 16), ("veintidós", 22), ("veintitres", 23), ("cien", 100),
    ("ciento once", 111), ("doscientos cincuenta", 250), ("quinientas", 500), ("mil quinientos", 1500),
    ("dos mil", 2000), ("tres mil quinientos veinte", 3520), ("treinta y siete y medio", 37.5),
    ("treinta y siete punto cinco", 37.5), ("cuarenta y un", 41), ("cero", 0), ("mil doce", 1012),
])
def test_spanish_number_words(text, value):
    assert value in ES.values(text)


@pytest.mark.parametrize("text,value", [
    ("le dieron dos disparos de narcan", 2), ("presión de ciento sesenta sobre noventa, pulso de ciento diez", 110),
    ("sats en noventa y dos en room air", 92), ("Presión Ciento Veinte", 120), ("le duele como un ocho de diez", 8),
])
def test_grounding_hears_spanish_and_code_switched_numbers(text, value):
    assert any(abs(v - value) < 0.05 for v in G.numbers_said(text))


def test_a_spanish_utterance_keeps_its_said_vitals_and_drops_invented_ones():
    t = "mi papá tiene la presión en ciento ochenta sobre cien y el azúcar le salió en cuatrocientos, respira rápido"
    assert G.supported("vitals.sbp", 180, t) and G.supported("vitals.dbp", 100, t)
    assert G.supported("vitals.glucose", 400, t)
    assert not G.supported("vitals.rr", 28, t) and not G.supported("vitals.hr", 110, t)


def test_spanish_doses_counts_and_pregnancy_weeks():
    assert G.supported("meds.given", {"drug": "naloxone", "count": 2}, "le dieron dos disparos de narcan")
    assert G.supported("meds.given", {"drug": "aspirin", "dose": 324}, "le dimos 324 de aspirina")
    assert G.supported("patient.pregnancy_weeks", 32, "tiene treinta y dos semanas de embarazo")
    assert not G.supported("patient.pregnancy_weeks", 30, "tiene siete meses de embarazo")


def test_spanish_words_that_name_a_key():
    assert G.supported("vitals.pain", 8, "me duele mucho, como un ocho de diez")
    assert G.supported("code_status", "DNR", "tiene una orden de no resucitar, está en el refri")
    assert G.supported("stroke.onset_witnessed", True, "yo la vi cuando se le torció la boca")
    assert G.supported("vitals.consciousness", "C", "está muy confundida, no sabe dónde está")
    assert not G.supported("code_status", "DNR", "quiere que hagan todo lo posible")


def test_english_words_are_not_read_as_spanish_numbers():
    """"once", "mil" and "coma" are Spanish number words but everyday English words: alone they never count."""
    assert 11 not in G.numbers_said("I'll grab a twelve lead once we're in the back")
    assert 1000 not in G.numbers_said("gave him five hundred mil of saline")
    assert G.spoken.spans("takes ozempic once a week") == []
    assert G.spoken.spans("found in a diabetic coma") == []            # "coma" is the Spanish decimal comma
    assert not G.supported("vitals.gcs_total", 11, "GCS changed once we moved him")


def test_english_readings_are_unchanged_by_adding_spanish():
    en = SpokenNumbers.from_config(load_yaml("numbers.yaml")["en"])
    for t in ["pressure's now one seventy over ninety eight", "a hundred and ten", "temp thirty seven point one",
              "so hes a dnr hes a hundred and one years old last vitals at six were one fifty over seventy ninety",
              "heparin four thousand units", "one thousand five hundred", "BP one oh two over sixty four"]:
        assert G.spoken.values(t) == en.values(t) and G.spoken.spans(t) == en.spans(t)


def test_accents_fold_one_character_for_one():
    assert fold_accents("veintidós, dieciséis, año") == "veintidos, dieciseis, ano"
    t = "le salió en ciento veintidós"
    assert ES.spans(t)[0][0] == t.index("ciento") and 122 in ES.spans(t)[0][1]


def test_languages_come_from_config_and_unknown_ones_fail():
    assert isinstance(G.spoken, SpokenNumberLanguages) and set(G.spoken.languages) == {"en", "es"}
    with pytest.raises(ValueError):
        SpokenNumberLanguages.from_config(load_yaml("numbers.yaml"), ["en", "xx"])
    rules = load_yaml("grounding.yaml")
    inline = Grounding({**rules, "spoken_numbers": load_yaml("numbers.yaml")["en"]})   # one inline table still works
    assert 160 in inline.numbers_said("one sixty") and 180 not in inline.numbers_said("ciento ochenta")
