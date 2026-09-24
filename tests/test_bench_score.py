"""The extraction scorer (eval/bench_extract.py, scorer v2): atomic facts, list items, time phrasing."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("bench", Path(__file__).resolve().parent.parent / "eval" / "bench_extract.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_time_phrasing_is_normalized_not_guessed():
    n = bench.norm_time
    assert n("since 3 a.m.") == n("3 am") == n("3am")
    assert n("fifteen minutes ago") == n("15 minutes ago")
    assert n("an hour ago") == n("1 hour ago")
    assert n("06:30") == n("0630") == n("6:30")
    assert n("nine fifteen") == n("9:15")
    assert n("since yesterday") == n("yesterday")
    assert n("for the past two hours") == n("2 hours")
    assert n("9:15") != n("9:50")                 # different times stay different
    assert n("10 pm") != n("10 am")


def test_list_items_are_scored_individually_and_unioned():
    gold = [("meds.list", ["clopidogrel", "metoprolol", "atorvastatin"], "medic")]
    pred = [("meds.list", ["clopidogrel", "metoprolol"], "medic"), ("meds.list", ["Lipitor"], "medic")]
    tp, fp, fn, role_ok, extra, missed = bench.score(gold, pred)
    assert (tp, fp, fn) == (2, 1, 1)
    assert extra == [("meds.list", "lipitor")] and missed == [("meds.list", "atorvastatin")]


def test_empty_list_is_a_fact():
    assert bench.score([("allergies", [], "patient")], [("allergies", [], "patient")])[:3] == (1, 0, 0)
    assert bench.score([("allergies", [], "patient")], [])[:3] == (0, 0, 1)


def test_scalars_and_roles():
    gold = [("vitals.sbp", 148, "medic"), ("patient.sex", "F", "medic")]
    pred = [("vitals.sbp", 148.0, "medic"), ("patient.sex", "f", "family"), ("vitals.temp", 37.0, "medic")]
    tp, fp, fn, role_ok, *_ = bench.score(gold, pred)
    assert (tp, fp, fn, role_ok) == (2, 1, 0, 1)


def test_free_text_is_presence_only():
    gold = [("complaint.chief", "chest pain", "medic")]
    pred = [("complaint.chief", "crushing substernal chest pain", "medic")]
    assert bench.score(gold, pred)[:3] == (0, 0, 0)
    assert bench.score(gold, pred, free_text=True)[:3] == (1, 0, 0)


def test_gfast_keys_are_scored_separately_not_as_false_positives():
    gold = [("vitals.sbp", 150, "medic")]
    pred = [("vitals.sbp", 150, "medic"), ("exam.gfast.facial", 1, "medic")]
    assert bench.score(gold, pred)[:3] == (1, 0, 0)


def test_spoken_vitals_are_grounded_even_when_other_digits_appear():
    from herald.extraction.grounding import default_grounding
    g = default_grounding()
    text = "72 year old male, BP one sixty over ninety"
    assert g.supported("vitals.sbp", 160, text) and g.supported("vitals.dbp", 90, text)
    assert not g.supported("vitals.hr", 88, "72 year old male, BP 160 over 90")   # an invented vital is still dropped


def test_row_confidence_follows_token_probabilities():
    import math
    from herald.extraction.confidence import row_confidences
    content = '{"f":[["vitals.hr",98,"m"],["vitals.consciousness","C","m"]]}'
    toks = [('{"f":[', 0.0), ('["vitals.hr",98,"m"]', math.log(0.99)), (",", 0.0),
            ('["vitals.consciousness","C","m"]', math.log(0.6)), ("]}", 0.0)]
    a, b = row_confidences(content, toks)
    assert round(a, 2) == 0.99 and round(b, 2) == 0.60


def test_a_record_is_scored_field_by_field_in_its_own_group():
    from eval.bench_extract import atoms, group_of, score
    gold = [("meds.given", {"drug": "aspirin", "dose": 324, "unit": "mg", "route": "PO"}, "medic")]
    pred = [("meds.given", {"drug": "aspirin", "dose": 324, "unit": "mg", "route": "IV"}, "medic")]
    g, p = atoms(gold), atoms(pred)
    assert len(set(g) & set(p)) == 3 and len(set(p) - set(g)) == 1     # right drug, dose, unit; wrong route
    assert group_of("meds.given") == "broad" and group_of("exam.gfast.facial") == "gfast"
    assert score(gold, pred)[:3] == (0, 0, 0)                          # not in the headline F1


def test_gold_rows_with_a_source_element_are_scored():
    from eval.bench_extract import score
    gold = [["allergies", ["aspirin"], "family", "daughter"], ["vitals.hr", 92, "medic"]]
    pred = [("allergies", ["aspirin"], "family"), ("vitals.hr", 92, "medic")]
    assert score(gold, pred)[:3] == (2, 0, 0)
