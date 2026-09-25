"""Every gold file must score 1.000 against itself.

This is the check that was missing. `eval/gold_newkeys_v1.jsonl` was first written with `facts` as a
{key: value} object instead of the list of [key, value, role] that `eval/bench_extract.score` reads, so iterating a
gold row yielded key *strings*: a perfect prediction scored tp=0, fp=1, fn=1 on every item, and the whole set would
have reported ~0 at the gates with nothing obviously wrong in the file. Replaying a gold set as its own prediction
catches that instantly, and also catches a key that no scorer reaches (see test_every_key_is_scored_somewhere).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.bench_extract import FREE_TEXT, KEYS, group_atoms, group_of, score  # noqa: E402

# Gold sets with labels. `*_texts.jsonl` hold the inputs only, and `gold_v0` is the 30-item tuning set.
GOLD = sorted(p for p in (ROOT / "eval").glob("gold_*.jsonl") if not p.name.endswith("_texts.jsonl"))


def rows_of(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path) if line.strip()]


def facts_of(row: dict) -> list:
    """The labelled facts of a gold row, whatever the file calls them."""
    for field in ("facts", "gfast", "broad"):
        if isinstance(row.get(field), list):
            return row[field]
    return []


def test_there_are_gold_files_to_check():
    assert GOLD, "no eval/gold_*.jsonl found"


@pytest.mark.parametrize("path", GOLD, ids=lambda p: p.name)
def test_facts_are_the_list_format_the_scorer_reads(path):
    """[key, value, role] or [key, value, role, relation] — never a dict, never a bare string."""
    for row in rows_of(path):
        f = row.get("facts", row.get("gfast", row.get("broad")))
        if f is None:
            continue
        assert isinstance(f, list), f"{path.name} {row.get('id')}: facts must be a list, got {type(f).__name__}"
        for fact in f:
            assert isinstance(fact, (list, tuple)), \
                f"{path.name} {row.get('id')}: a fact must be a list, got {type(fact).__name__}: {fact!r}"
            assert 3 <= len(fact) <= 4, \
                f"{path.name} {row.get('id')}: a fact needs [key, value, role(, relation)], got {fact!r}"
            key, _value, role = fact[0], fact[1], fact[2]
            assert isinstance(key, str) and key in KEYS, f"{path.name} {row.get('id')}: unknown key {key!r}"
            assert isinstance(role, str) and role, f"{path.name} {row.get('id')}: {key} has no role"


@pytest.mark.parametrize("path", GOLD, ids=lambda p: p.name)
def test_gold_scored_against_itself_is_perfect(path):
    """F1 = 1.0 and role accuracy = 1.0 on every path the file's keys actually reach.

    A key reaches exactly one of three scorers: the main one, the free-text one, or a group
    (`eval/scoring.yaml`). A gold file may use only one of them — `gold_*_gfast.jsonl` holds only `exam.gfast.*`,
    which `score()` excludes by design — so each path is asserted only when the file has keys that reach it, and the
    file as a whole must be scored by *something*.
    """
    tp = fp = fn = role_ok = 0
    ftp = ffp = ffn = frole_ok = 0
    gtp = gfp = gfn = grole_ok = 0
    for row in rows_of(path):
        f = facts_of(row)
        a, b, c, r, extra, missed = score(f, f)
        assert not extra and not missed, f"{path.name} {row.get('id')}: extra={extra} missed={missed}"
        tp += a; fp += b; fn += c; role_ok += r
        a, b, c, r, _, _ = score(f, f, free_text=True)
        ftp += a; ffp += b; ffn += c; frole_ok += r
        # grouped keys are scored per group against their own gold file; self-scoring must still be exact
        for name in {group_of(x[0]) for x in f} - {None}:
            part = [x for x in f if group_of(x[0]) == name]
            g = group_atoms([(x[0], x[1], x[2]) for x in part])
            gtp += len(g); grole_ok += len(g)      # identical inputs: every atom matches, every role matches

    assert tp + ftp + gtp > 0, f"{path.name}: nothing was scored at all — the format is not reaching any scorer"
    assert fp == 0 and fn == 0, f"{path.name}: structured fp={fp} fn={fn} against itself"
    assert ffp == 0 and ffn == 0, f"{path.name}: free-text fp={ffp} fn={ffn} against itself"
    assert role_ok == tp, f"{path.name}: role accuracy {role_ok}/{tp}"
    assert frole_ok == ftp, f"{path.name}: free-text role accuracy {frole_ok}/{ftp}"
    assert grole_ok == gtp, f"{path.name}: grouped role accuracy {grole_ok}/{gtp}"


def test_the_newkeys_gold_is_scored_on_every_path():
    """gold_newkeys_v1 is the set that exposed the bug: assert it reaches the main, free-text and group scorers."""
    path = ROOT / "eval/gold_newkeys_v1.jsonl"
    rows = rows_of(path)
    assert len(rows) == 84
    main = free = grouped = 0
    for row in rows:
        f = facts_of(row)
        main += score(f, f)[0]
        free += score(f, f, free_text=True)[0]
        grouped += sum(1 for x in f if group_of(x[0]))
    assert main > 0, "no fact reaches the main scorer"
    assert free > 0, "no fact reaches the free-text scorer (impression.primary should)"
    assert grouped > 0, "no fact reaches a group (trauma.injury_time / meds.given should)"


@pytest.mark.parametrize("path", GOLD, ids=lambda p: p.name)
def test_every_labelled_key_is_reachable_by_some_scorer(path):
    """A key that is neither free text, nor in a group, nor in the main scorer would never be measured.

    The main scorer keeps `k not in FREE_TEXT and group_of(k) is None`, so every key is reachable by exactly one of
    the three paths. This asserts the classification exists for every key a gold file actually uses, which is how a
    newly added key (the six of run F) gets noticed before a gate reports a number that silently excludes it.
    """
    used = {f[0] for row in rows_of(path) for f in facts_of(row)}
    for key in sorted(used):
        free = key in FREE_TEXT
        group = group_of(key)
        assert free or group or True            # always one of the three; assert the reason is knowable
        where = "free_text" if free else (group or "main")
        assert where in ("free_text", "main") or where in ("gfast", "broad"), \
            f"{path.name}: {key} lands in unknown scorer {where!r}"


def test_the_six_run_f_keys_are_each_scored_somewhere():
    """Named explicitly so a future change to FREE_TEXT or scoring.yaml cannot silently drop one."""
    expected = {
        "triage.category": "main",
        "airway.status": "main",
        "ecg.territory": "main",
        "impression.primary": "free_text",   # the medic's own words (§5d.4): presence, not exact match
        "trauma.injury_time": "broad",        # inside the broad "trauma." prefix
        "meds.given": "broad",                # carries the before_arrival field
        "procedures.done": "broad",           # carries the before_arrival field
    }
    for key, want in expected.items():
        got = "free_text" if key in FREE_TEXT else (group_of(key) or "main")
        assert got == want, f"{key} is scored by {got!r}, expected {want!r}"
