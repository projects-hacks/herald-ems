"""The photo bench's gold loader accepts the two shapes the repo's photo sets are written in.

`eval/photos/gold.jsonl` (the synthetic set) writes `facts` as a list of [key, value] pairs. The sets written by
hand afterwards write it as a {key: value} object, leave `degradations` out, and mark a row `needs_check` when the
labeler was not certain of the value: `data/photos/real/labels.jsonl` (real phone photos), `eval/forms_polst/
gold.jsonl` (POLST forms) and `data/photos/web/labels.jsonl` (openly licensed monitor photos). All of them must
score through the same code as the synthetic set, so the numbers are comparable.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.visionbench import photos                      # noqa: E402
from eval.visionbench.photo_scoring import aggregate, score_item      # noqa: E402

PROMPT = "Read vitals.hr and vitals.spo2 from the screen."


def write_gold(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "labels.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


# ---------------------------------------------------------------- the two shapes


def test_object_facts_become_pairs_and_list_facts_are_left_alone():
    obj = photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {"vitals.hr": 75}})
    assert obj["facts"] == [["vitals.hr", 75]]
    pairs = photos.normalize_row({"file": "b.jpg", "mode": "monitor", "facts": [["vitals.hr", 75]],
                                  "degradations": ["glare"]})
    assert pairs["facts"] == [["vitals.hr", 75]]
    assert pairs["degradations"] == ["glare"]


def test_empty_facts_mean_the_answer_is_nothing():
    """An empty object is a real label, not a missing one: the image shows no clinical value."""
    row = photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {}})
    assert row["facts"] == []
    assert score_item(row, [], PROMPT)["no_fact_image"] is True
    assert score_item(row, [], PROMPT)["false_fact"] is False


def test_a_fact_read_from_a_no_fact_image_is_a_false_fact():
    row = photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {}})
    s = score_item(row, [["vitals.hr", 88]], PROMPT)
    assert s["false_fact"] is True and s["exact"] is False


def test_missing_facts_key_is_treated_as_no_facts():
    assert photos.normalize_row({"file": "a.jpg", "mode": "monitor"})["facts"] == []


def test_degradations_default_to_empty_so_aggregate_does_not_need_them():
    """Regression: the hand-written sets have no `degradations`, and aggregate() indexes it for every image."""
    rows = [photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {"vitals.hr": 75}})]
    items = [{"file": r["file"], "line": r, "score": score_item(r, [["vitals.hr", 75]], PROMPT),
              "strength_ok": None, "error": None, "json_invalid": False} for r in rows]
    out = aggregate(items)
    assert out["f1"] == 1.0 and out["per_degradation"]["clean"]["n"] == 1


# ---------------------------------------------------------------- needs_check


def test_needs_check_rows_get_their_own_image_set():
    """So one run reports every image and the confident ones separately (real photos: 97 and 80)."""
    confident = photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {"vitals.hr": 75}})
    uncertain = photos.normalize_row({"file": "b.jpg", "mode": "monitor", "facts": {"vitals.hr": 75},
                                      "needs_check": True})
    assert confident["set"] == "confident" and uncertain["set"] == "needs_check"


def test_an_explicit_set_is_never_overwritten():
    row = photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {}, "set": "screens",
                                "needs_check": True})
    assert row["set"] == "screens"


def test_per_set_splits_the_run_into_confident_and_needs_check():
    rows = [photos.normalize_row({"file": "a.jpg", "mode": "monitor", "facts": {"vitals.hr": 75}}),
            photos.normalize_row({"file": "b.jpg", "mode": "monitor", "facts": {"vitals.hr": 60},
                                  "needs_check": True})]
    preds = [[["vitals.hr", 75]], [["vitals.hr", 99]]]        # the confident one right, the uncertain one wrong
    items = [{"file": r["file"], "line": r, "score": score_item(r, p, PROMPT), "strength_ok": None,
              "error": None, "json_invalid": False} for r, p in zip(rows, preds)]
    out = aggregate(items)
    assert out["per_set"]["confident"]["n"] == 1 and out["per_set"]["confident"]["f1"] == 1.0
    assert out["per_set"]["needs_check"]["n"] == 1 and out["per_set"]["needs_check"]["f1"] == 0.0
    assert out["n"] == 2                                      # the headline still covers every image


# ---------------------------------------------------------------- loading and the image folder


def test_load_gold_reads_a_custom_file_and_filters(tmp_path):
    p = write_gold(tmp_path, [{"file": "a.jpg", "mode": "monitor", "facts": {"vitals.hr": 75}},
                              {"file": "b.jpg", "mode": "pill_bottle", "facts": {}}])
    assert [r["file"] for r in photos.load_gold(p)] == ["a.jpg", "b.jpg"]
    assert [r["file"] for r in photos.load_gold(p, only={"a"})] == ["a.jpg"]        # by stem
    assert [r["file"] for r in photos.load_gold(p, only={"b.jpg"})] == ["b.jpg"]    # by file name
    assert [r["file"] for r in photos.load_gold(p, limit=1)] == ["a.jpg"]
    assert photos.load_gold(p)[0]["facts"] == [["vitals.hr", 75]]


def test_read_one_takes_the_image_from_the_given_folder(tmp_path):
    """--photo-dir, so a gold file can live apart from its images (and the default stays eval/photos/)."""
    (tmp_path / "a.jpg").write_bytes(b"JPGBYTES")
    seen = {}

    class Reader:
        def read(self, image, mode, photo_id=None):
            seen["image"], seen["mode"] = image, mode
            return []

    class Model:
        calls: list = []

    photos.read_one(Reader(), Model(), {"file": "a.jpg", "mode": "monitor"}, tmp_path)
    assert seen == {"image": b"JPGBYTES", "mode": "monitor"}


def test_read_one_reports_a_missing_image_instead_of_scoring_it(tmp_path):
    class Reader:
        def read(self, *a, **kw):
            raise AssertionError("must not be called when the file is missing")

    class Model:
        calls: list = []

    with pytest.raises(FileNotFoundError):
        photos.read_one(Reader(), Model(), {"file": "nope.jpg", "mode": "monitor"}, tmp_path)


# ---------------------------------------------------------------- the real files on disk


@pytest.mark.parametrize("rel,n", [("data/photos/real/labels.jsonl", 97), ("eval/forms_polst/gold.jsonl", 60)])
def test_the_checked_in_photo_sets_load_and_score(rel, n):
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} is not in this clone")
    rows = photos.load_gold(path)
    assert len(rows) == n
    for r in rows:
        assert isinstance(r["facts"], list) and r["set"] in ("confident", "needs_check")
        score_item(r, [], PROMPT)            # every row is scorable, including the empty-facts ones
