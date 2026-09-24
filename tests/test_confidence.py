"""Per-fact confidence from token probabilities (herald/extraction/confidence.py).

The toy output mirrors the live test: the model hesitated over which vital to write first (systolic 0.37 vs
temperature 0.32 ...) while the value itself was certain. That hesitation is about output order, not correctness."""
import math

from herald.extraction.confidence import row_confidences, row_spans

L = math.log
CONTENT = '{"f":[["vitals.sbp",182,"m"],["vitals.temp",37.1,"m"]]}'
TOKENS = [('{"f":[["', 0.0, []), ("vitals", 0.0, []),
          (".s", L(.37), [(".s", L(.37)), (".temp", L(.32)), (".on", L(.15)), (".con", L(.12))]),
          ("bp", L(.84), [("bp", L(.84)), ("po", L(.16))]), ('",', 0.0, []), ("182", 0.0, []), (',"', 0.0, []),
          ("m", 0.0, []), ('"],["', L(.7), []), ("vitals", 0.0, []),
          (".temp", L(.6), [(".temp", L(.6)), (".con", L(.38))]), ('",', 0.0, []), ("37", 0.0, []),
          (".1", L(.9), []), (',"', 0.0, []), ("m", 0.0, []), ('"]', L(.71), []), ("]}", 0.0, [])]


def test_tokens_rebuild_the_output():
    assert "".join(t[0] for t in TOKENS) == CONTENT and len(row_spans(CONTENT)) == 2


def test_joint_counts_every_token_of_the_row():
    assert [round(x, 3) for x in row_confidences(CONTENT, TOKENS, "joint")] == [0.218, 0.268]


def test_value_ignores_which_fact_came_next():
    assert [round(x, 3) for x in row_confidences(CONTENT, TOKENS, "value")] == [1.0, 0.9]


def test_order_free_counts_keys_written_later_as_agreement_and_others_as_doubt():
    # row 1: ".s" 0.37 + ".temp" 0.32 (written next) = 0.69; ".on"/".con" are never written -> doubt; "bp" 0.84
    # row 2: ".temp" 0.6 (".con" never written); value ".1" 0.9
    assert [round(x, 3) for x in row_confidences(CONTENT, TOKENS, "order_free")] == [0.58, 0.54]


def test_two_tuple_tokens_still_work():
    two = [(t[0], t[1]) for t in TOKENS]
    assert row_confidences(CONTENT, two, "joint") == row_confidences(CONTENT, TOKENS, "joint")
