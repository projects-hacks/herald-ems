"""The run F gate engine (scripts/run_gates.py) and the gate table it runs (config/gates.yaml).

No bench is called, no model is served and no network socket is opened: every test feeds fake result records to the
pure functions, and the `--dry-run` test asserts that subprocess and urllib are never reached. These functions decide
whether a fine-tuned adapter ships (docs/TRAINING_PLAN.md §6, §6a, §6b), so the cases here are the ones where a wrong
answer would be silent: a missing metric, a missing baseline, an operator applying its margin the wrong way.
"""
import json
from pathlib import Path

import pytest
import yaml

from scripts import run_gates as rg

ROOT = Path(__file__).resolve().parent.parent
GATES_YAML = yaml.safe_load((ROOT / "config" / "gates.yaml").read_text())


def rec(level, gate, run=1, **metrics):
    """One results.jsonl record, as run_one would append it."""
    return {"level": level, "label": level, "gate": gate, "group": "speech", "run": run, "exit": 0,
            "seconds": 1.0, "metrics": dict(metrics), "ts": "2026-09-25 10:00:00"}


# ───────────────────────────── dig ─────────────────────────────

def test_dig_walks_a_dotted_path():
    line = {"f1": 0.93, "groups": {"broad": {"f1": 0.88, "recall": 0.9}}}
    assert rg.dig(line, "f1") == 0.93
    assert rg.dig(line, "groups.broad.f1") == 0.88


def test_dig_returns_none_for_a_missing_hop():
    line = {"groups": {"broad": {"f1": 0.88}}}
    assert rg.dig(line, "groups.narrow.f1") is None      # middle hop missing
    assert rg.dig(line, "groups.broad.precision") is None  # leaf missing
    assert rg.dig(line, "missing") is None
    assert rg.dig(line, "groups.broad.f1.more") is None  # hop through a float, not a dict
    assert rg.dig({}, "f1") is None


def test_dig_keeps_a_falsy_value():
    """0 invented facts is a result, not a missing metric: the difference decides the photo gates."""
    assert rg.dig({"false_fact_images": 0}, "false_fact_images") == 0


# ───────────────────────── json_lines / pick ─────────────────────────

BENCH_STDOUT = """\
loading gold eval/gold_v2.jsonl (148 items)
item 12/148 ...
{ not json at all }
{"bench": "vision:photos", "f1": 0.981, "false_fact_images": 0}
prompt cache warm
{"bench": "vision:rerank", "top1": 0.788, "top3": 0.827}
done in 41.2s
"""


def test_json_lines_skips_progress_output():
    lines = rg.json_lines(BENCH_STDOUT)
    assert [ln.get("bench") for ln in lines] == ["vision:photos", "vision:rerank"]


def test_json_lines_on_no_result_at_all():
    assert rg.json_lines("loading...\ntraceback\n") == []
    assert rg.json_lines("") == []


def test_pick_uses_the_select_field():
    lines = rg.json_lines(BENCH_STDOUT)
    assert rg.pick(lines, {"bench": "vision:photos"})["f1"] == 0.981
    assert rg.pick(lines, {"bench": "vision:rerank"})["top1"] == 0.788


def test_pick_matches_a_numeric_select_across_types():
    """config/gates.yaml has `select: {threshold: 0.8}` and the bench prints 0.8 as a number."""
    lines = [{"header": 1}, {"threshold": 0.7, "wrong_auto": 0}, {"threshold": 0.8, "wrong_auto": 1}]
    assert rg.pick(lines, {"threshold": 0.8})["wrong_auto"] == 1


def test_pick_falls_back_to_the_last_line_without_select():
    lines = rg.json_lines(BENCH_STDOUT)
    assert rg.pick(lines, None)["bench"] == "vision:rerank"
    assert rg.pick(lines, {})["bench"] == "vision:rerank"


def test_pick_returns_none_when_nothing_matches():
    assert rg.pick(rg.json_lines(BENCH_STDOUT), {"bench": "vision:flowchart"}) is None
    assert rg.pick([], None) is None


# ───────────────────────────── medians ─────────────────────────────

def test_medians_and_spread():
    recs = [rec("f-e2", "gold_v2", 1, f1=0.91), rec("f-e2", "gold_v2", 2, f1=0.93),
            rec("f-e2", "gold_v2", 3, f1=0.92)]
    assert rg.medians(recs, "f1") == (0.92, [0.91, 0.92, 0.93])


def test_medians_ignores_runs_missing_the_metric():
    """A bench that errored on one run records no metrics; the median is of what was measured, not 0."""
    recs = [rec("f-e2", "g", 1, f1=0.90), rec("f-e2", "g", 2), rec("f-e2", "g", 3, f1=0.94)]
    med, spread = rg.medians(recs, "f1")
    assert med == pytest.approx(0.92) and spread == [0.90, 0.94]   # the mean of two, not a third value of 0
    assert rg.medians(recs, "gfast_f1") == (None, [])


def test_medians_on_no_records_and_on_non_numbers():
    assert rg.medians([], "f1") == (None, [])
    assert rg.medians([rec("f-e2", "g", 1, f1="n/a")], "f1") == (None, [])
    assert rg.medians([{"gate": "g", "run": 1}], "f1") == (None, [])   # record with no metrics key at all


# ───────────────────────────── verdict ─────────────────────────────

def one_row(gate, records, baseline=None):
    rows = rg.verdict(gate, records, baseline)
    assert len(rows) == 1
    return rows[0]


def test_verdict_ge_against_a_constant():
    gate = {"id": "gold_v3", "checks": [{"metric": "f1", "op": ">=", "value": 0.92}]}
    assert one_row(gate, [rec("f-e2", "gold_v3", 1, f1=0.92)])["pass"] is True    # the boundary passes
    assert one_row(gate, [rec("f-e2", "gold_v3", 1, f1=0.9199)])["pass"] is False


def test_verdict_le_against_a_constant():
    gate = {"id": "calibration", "checks": [{"metric": "wrong_auto", "op": "<=", "value": 1}]}
    assert one_row(gate, [rec("f-e2", "calibration", 1, wrong_auto=1)])["pass"] is True
    assert one_row(gate, [rec("f-e2", "calibration", 1, wrong_auto=2)])["pass"] is False


def test_verdict_not_worse_than_subtracts_the_margin_from_the_baseline():
    """§6 'CI lower bound > -0.01': 0.01 below E v2 still passes, more than that does not."""
    gate = {"id": "gold_v2", "checks": [{"metric": "f1", "op": "not_worse_than", "vs": "baseline", "margin": 0.01}]}
    base = [rec("e-v2", "gold_v2", r, f1=0.90) for r in (1, 2, 3)]
    row = one_row(gate, [rec("f-e2", "gold_v2", 1, f1=0.895)], base)
    assert (row["baseline"], row["want"], row["pass"]) == (0.90, 0.89, True)
    assert one_row(gate, [rec("f-e2", "gold_v2", 1, f1=0.89)], base)["pass"] is True
    assert one_row(gate, [rec("f-e2", "gold_v2", 1, f1=0.88)], base)["pass"] is False


def test_verdict_not_above_adds_the_margin_to_the_baseline():
    """§6 'p95 <= E v2's': the margin moves the bar UP, never down."""
    gate = {"id": "gold_v2", "checks": [{"metric": "p95", "op": "not_above", "vs": "baseline", "margin": 0}]}
    base = [rec("e-v2", "gold_v2", 1, p95=900.0)]
    assert one_row(gate, [rec("f-e2", "gold_v2", 1, p95=900.0)], base)["pass"] is True
    assert one_row(gate, [rec("f-e2", "gold_v2", 1, p95=901.0)], base)["pass"] is False

    slack = {"id": "g", "checks": [{"metric": "p95", "op": "not_above", "vs": "baseline", "margin": 50}]}
    row = one_row(slack, [rec("f-e2", "g", 1, p95=940.0)], base)
    assert (row["want"], row["pass"]) == (950, True)


def test_verdict_is_pending_when_the_baseline_was_not_run():
    """The failure that must never read as a pass: no baseline level measured."""
    gate = {"id": "photos_real", "checks": [{"metric": "f1", "op": "not_worse_than", "vs": "baseline", "margin": 0}]}
    row = one_row(gate, [rec("f-e2", "photos_real", 1, f1=0.99)], baseline=None)
    assert row["pass"] is None
    assert row["baseline"] is None
    assert row["want"] == "not_worse_than baseline"
    assert one_row(gate, [rec("f-e2", "photos_real", 1, f1=0.99)], baseline=[])["pass"] is None
    # ... and when the baseline ran but not this metric
    assert one_row(gate, [rec("f-e2", "photos_real", 1, f1=0.99)],
                   [rec("untuned-vision", "photos_real", 1, invented=0)])["pass"] is None


def test_verdict_is_pending_when_the_level_itself_has_no_number():
    gate = {"id": "gold_v3", "checks": [{"metric": "f1", "op": ">=", "value": 0.92}]}
    row = one_row(gate, [rec("f-e2", "gold_v3", 1)])
    assert row["pass"] is None and row["want"] == 0.92


def test_verdict_reports_every_check_of_a_gate():
    gate = {"id": "rerank", "checks": [{"metric": "top1", "op": ">=", "value": 0.788},
                                       {"metric": "top3", "op": ">=", "value": 0.827},
                                       {"metric": "refusals", "op": ">=", "value": 0.571}]}
    rows = rg.verdict(gate, [rec("f-e2", "rerank", 1, top1=0.80, top3=0.80, refusals=0.571)])
    assert [r["pass"] for r in rows] == [True, False, True]


def test_verdict_of_a_gate_with_no_checks_is_empty():
    assert rg.verdict({"id": "calibration_sweep", "report_only": True}, [rec("f-e2", "calibration_sweep", 1)]) == []


# ───────────────────────────── applicable ─────────────────────────────

def test_applicable_gate():
    ok, why = rg.applicable({"id": "gold_v2", "group": "speech"}, {"groups": ["speech", "photos"]})
    assert ok and why == ""


def test_applicable_skips_a_group_the_level_has_no_role_for():
    ok, why = rg.applicable({"id": "rerank", "group": "kept"}, {"groups": ["speech"]})
    assert ok is False and "kept" in why
    assert rg.applicable({"id": "rerank", "group": "kept"}, {})[0] is False   # level with no groups at all


def test_applicable_skips_a_gate_whose_requires_file_is_absent(tmp_path, monkeypatch):
    gate = {"id": "photos_web", "group": "photos", "requires_file": "data/photos/web/labels.jsonl"}
    monkeypatch.setattr(rg, "ROOT", tmp_path)
    ok, why = rg.applicable(gate, {"groups": ["photos"]})
    assert ok is False and why == "needs data/photos/web/labels.jsonl"

    (tmp_path / "data" / "photos" / "web").mkdir(parents=True)
    (tmp_path / "data" / "photos" / "web" / "labels.jsonl").write_text("{}\n")
    assert rg.applicable(gate, {"groups": ["photos"]})[0] is True


def test_applicable_skips_manual_gates_even_in_their_own_group():
    gate = {"id": "translation_spot_check", "group": "kept", "manual": True, "blocking": True}
    ok, why = rg.applicable(gate, {"groups": ["kept"]})
    assert ok is False and why == "judged by a human"


# ───────────────────────── the plan (--dry-run) ─────────────────────────

PLAN_CFG = {
    "runs": 3, "need_gib": 6, "endpoint": "http://127.0.0.1:8080/v1",
    "results": "runs/gates/results.jsonl", "report_dir": "runs/gates",
    "levels": {"e-v2": {"label": "ems-e-v2-fp8", "serve": "ems", "groups": ["speech"], "baseline_for": ["speech"]},
               "f-e2": {"label": "herald-f", "repo": "acme/f", "groups": ["speech", "kept"]}},
    "gates": [{"id": "gold_v3", "group": "speech", "cmd": ["eval/bench_extract.py", "--model", "{label}",
                                                          "--dump", "{dump}"], "metrics": {"f1": "f1"}},
              {"id": "rerank", "group": "kept", "blocking": True, "cmd": ["eval/vision_bench.py", "--model",
                                                                         "{label}"], "metrics": {"top1": "top1"}},
              {"id": "soak", "group": "demo", "manual": True}],
}


def test_plan_lists_every_level_gate_and_run():
    lines = rg.plan_lines(PLAN_CFG, ["e-v2", "f-e2"], runs=3)
    text = "\n".join(lines)
    assert "=== e-v2 (ems-e-v2-fp8): 1 gates x 3 runs ===" in text
    assert "=== f-e2 (herald-f): 2 gates x 3 runs ===" in text
    assert "[skip] e-v2/rerank: level has no kept role" in text
    assert text.count("eval/bench_extract.py") == 6      # 2 levels x 3 runs
    assert text.count("eval/vision_bench.py") == 3       # f-e2 only
    assert "plan: 9 bench run(s) over 2 level(s); 1 manual gate(s) a person judges (soak)" in text
    assert lines[-1] == "dry run: nothing was served, called or written."


def test_plan_commands_go_through_run_job_and_carry_the_label_and_dump():
    lines = rg.plan_lines(PLAN_CFG, ["f-e2"], runs=1, want_gates={"gold_v3"})
    cmd = next(ln for ln in lines if "bench_extract" in ln).split()
    assert cmd[0].endswith("scripts/run_job.py")         # MEMORY_SAFETY §4: never the bench alone
    assert "--need-gib" in cmd and cmd[cmd.index("--need-gib") + 1] == "6"
    assert cmd[cmd.index("--model") + 1] == "herald-f"
    assert cmd[cmd.index("--dump") + 1].endswith("eval/dumps/gates/f-e2/gold_v3_run1.jsonl")


def test_plan_names_the_detached_serve_command_it_will_not_run():
    e_v2, f_e2 = (rg.plan_lines(PLAN_CFG, [lid], runs=1) for lid in ("e-v2", "f-e2"))
    assert any("scripts/serve_models.sh ems" in ln for ln in e_v2)
    assert any("setsid nohup" in ln and "acme/f" in ln for ln in f_e2)


def test_plan_counts_only_the_runs_still_missing():
    seen = {("f-e2", "gold_v3", 1), ("f-e2", "gold_v3", 2)}
    text = "\n".join(rg.plan_lines(PLAN_CFG, ["f-e2"], runs=3, want_gates={"gold_v3"}, seen=seen))
    assert "gold_v3: 1 of 3 run(s) to do (2 already recorded)" in text
    assert text.count("bench_extract") == 1
    assert "plan: 1 bench run(s)" in text


def test_plan_filters_by_group():
    text = "\n".join(rg.plan_lines(PLAN_CFG, ["f-e2"], runs=1, want_groups={"kept"}))
    assert "vision_bench" in text and "bench_extract" not in text


def test_plan_runs_nothing_at_all(monkeypatch):
    """--dry-run while a 30B is loading: no subprocess, no socket, no directory, no dump file."""
    def boom(*_a, **_k):
        raise AssertionError("--dry-run must not touch anything")

    monkeypatch.setattr(rg.subprocess, "run", boom)
    monkeypatch.setattr(rg.urllib.request, "urlopen", boom)
    monkeypatch.setattr(rg, "served", boom)
    monkeypatch.setattr(Path, "mkdir", boom)
    monkeypatch.setattr(Path, "write_text", boom)
    monkeypatch.setattr(Path, "open", boom)
    assert rg.plan_lines(PLAN_CFG, ["e-v2", "f-e2"], runs=3)


def test_plan_against_the_real_gate_table():
    cfg = rg.load_gates(ROOT / "config" / "gates.yaml")
    lines = rg.plan_lines(cfg, list(cfg["levels"]), runs=cfg["runs"])
    assert sum(1 for ln in lines if ln.startswith("=== ")) == len(cfg["levels"])
    assert any(ln.startswith("plan: ") for ln in lines)


# ───────────────────────── results.jsonl ─────────────────────────

def test_read_results_on_an_absent_or_empty_file(tmp_path):
    """--report-only before anything has run: nothing measured, not a crash."""
    assert rg.read_results(tmp_path / "results.jsonl") == []
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert rg.read_results(empty) == []
    blank = tmp_path / "blank.jsonl"
    blank.write_text("\n\n")
    assert rg.read_results(blank) == []


def test_read_results_parses_the_recorded_runs(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text("".join(json.dumps(rec("f-e2", "gold_v3", r, f1=0.9)) + "\n" for r in (1, 2)))
    got = rg.read_results(path)
    assert [(r["level"], r["run"]) for r in got] == [("f-e2", 1), ("f-e2", 2)]


def test_load_gates_rejects_an_unknown_check_operator(tmp_path):
    bad = dict(PLAN_CFG, gates=[{"id": "gold_v3", "group": "speech", "cmd": ["x"], "metrics": {"f1": "f1"},
                                 "checks": [{"metric": "f1", "op": "much_better_than", "value": 0.9}]}])
    path = tmp_path / "gates.yaml"
    path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="gold_v3:much_better_than"):
        rg.load_gates(path)


# ───────────────────────── ship_decision (§6a / §6b) ─────────────────────────

SHIP_CFG = {"levels": {"e-v2": {}, "untuned-vision": {}, "f4b": {}, "f-e1": {}, "f-e2": {}}}
FALLBACK_OPTIONS = ("herald-f4b-fp8", "§7a", "ems-e-v2-fp8")


def ship(blocked, unmeasured=None, manual=()):
    return "\n".join(rg.ship_decision(SHIP_CFG, blocked, unmeasured, manual))


def test_ship_decision_clears_epoch_2_when_every_blocking_gate_passes():
    text = ship({})
    assert "f-e2: passes every blocking gate" in text
    assert "`herald-f` (epoch 2) may ship" in text


def test_ship_decision_will_not_clear_epoch_2_on_unmeasured_blocking_gates():
    text = ship({}, unmeasured={"f-e2": ["rerank"]})
    assert "may ship" not in text
    assert "kept-ability gate(s) not measured: rerank" in text


def test_ship_decision_counts_a_manual_blocking_gate_as_unmeasured_for_every_epoch():
    text = ship({}, manual=["translation_spot_check"])
    assert "may ship" not in text
    for lid in ("f-e1", "f-e2"):
        assert f"- {lid}: no blocking failure so far, but 1 kept-ability gate(s) not measured" in text


def test_ship_decision_blocks_the_epoch_that_failed_a_kept_ability_gate():
    text = ship({"f-e2": ["rerank (top1 0.71)"]})
    assert "**f-e2: cannot ship** — failed rerank (top1 0.71)" in text


def test_ship_decision_points_at_the_fallback_not_epoch_1(monkeypatch):
    """§6b: epoch 2 beat epoch 1 on all three dev splits, so epoch 1 is NOT the fallback when epoch 2 fails."""
    text = ship({"f-e2": ["figure (added_words 0.04)"]}, unmeasured={"f-e1": ["rerank", "figure"]})
    assert "epoch 1 is NOT the fallback" in text
    for option in FALLBACK_OPTIONS:
        assert option in text
    # the numbered options a person is told to take must not be "ship epoch 1"
    options = [ln for ln in text.splitlines() if ln.lstrip().startswith(("1.", "2.", "3."))]
    assert options, "the fallback options must be listed"
    assert not any("epoch 1" in o or "f-e1" in o or "herald-f-e1" in o for o in options)
    assert "0.1393" in text and "0.1322" in text      # the measured replay losses the rule rests on


def test_ship_decision_does_not_promote_a_clean_epoch_1_over_a_blocked_epoch_2():
    """Epoch 1 passing is not a reason to ship it: §6a rule 2 is superseded."""
    text = ship({"f-e2": ["rerank (top1 0.70)"]})
    assert "f-e1: passes every blocking gate" in text          # stated as a fact
    assert "may ship" not in text                              # but never cleared to ship
    assert "epoch 1 is NOT the fallback" in text
    assert "last resort" in text


def test_ship_decision_is_silent_without_epoch_levels():
    assert rg.ship_decision({"levels": {"e-v2": {}, "untuned-vision": {}}}, {}) == []


# ───────────────────────────── report ─────────────────────────────

REPORT_CFG = {
    "runs": 1, "need_gib": 6, "endpoint": "x", "results": "r.jsonl", "report_dir": "out",
    "levels": {"untuned-vision": {"label": "qwen3vl-fp8", "groups": ["photos", "kept"],
                                  "baseline_for": ["photos", "kept"]},
               "f-e2": {"label": "herald-f", "groups": ["photos", "kept"]}},
    "gates": [{"id": "photos_synthetic", "group": "photos", "title": "eval/photos",
               "cmd": ["eval/vision_bench.py"], "metrics": {"f1": "f1"},
               "checks": [{"metric": "f1", "op": ">=", "value": 0.98}]},
              {"id": "rerank", "group": "kept", "blocking": True, "title": "protocol reranking",
               "cmd": ["eval/vision_bench.py"], "metrics": {"top1": "top1"},
               "checks": [{"metric": "top1", "op": ">=", "value": 0.788}]},
              {"id": "translation_spot_check", "group": "kept", "blocking": True, "manual": True,
               "title": "10 EN<->ES lines"}],
}


def photo_recs(f1_base, f1_cand, top1_base, top1_cand):
    return [{**rec("untuned-vision", "photos_synthetic", 1, f1=f1_base), "group": "photos"},
            {**rec("f-e2", "photos_synthetic", 1, f1=f1_cand), "group": "photos"},
            {**rec("untuned-vision", "rerank", 1, top1=top1_base), "group": "kept"},
            {**rec("f-e2", "rerank", 1, top1=top1_cand), "group": "kept"}]


def row_for(md, gate_id, level):
    """The report row for one (gate, level), from the table under that gate's heading."""
    body = md.split(f"### {gate_id} ")[1].split("###")[0]
    return next(ln for ln in body.splitlines() if ln.startswith(f"| {level} |"))


def test_report_marks_a_failing_check_FAIL_and_a_passing_one_PASS():
    md = rg.report(REPORT_CFG, photo_recs(0.99, 0.97, 0.80, 0.80))
    assert "**FAIL**" in row_for(md, "photos_synthetic", "f-e2")
    assert row_for(md, "rerank", "f-e2").endswith("| PASS |")
    assert "photos/photos_synthetic/f-e2: f1 0.97 >= 0.98" in md
    assert "- FAIL: 1" in md


def test_report_marks_a_blocking_failure_distinctly():
    md = rg.report(REPORT_CFG, photo_recs(0.99, 0.99, 0.80, 0.70))
    blocking, ordinary = row_for(md, "rerank", "f-e2"), row_for(md, "photos_synthetic", "f-e2")
    assert "**FAIL (blocks shipping)**" in blocking
    assert ordinary.endswith("| PASS |")
    assert "**f-e2: cannot ship** — failed rerank (top1 0.7)" in md


def test_report_calls_the_baseline_level_baseline_not_pass():
    md = rg.report(REPORT_CFG, photo_recs(0.99, 0.99, 0.80, 0.80))
    assert row_for(md, "photos_synthetic", "untuned-vision").endswith("| baseline |")


def test_report_shows_the_spread_when_the_runs_disagree():
    recs = [{**rec("f-e2", "photos_synthetic", r, f1=v), "group": "photos"}
            for r, v in ((1, 0.97), (2, 0.99), (3, 0.98))]
    md = rg.report(REPORT_CFG, recs)
    assert "0.98 [0.97–0.99]" in row_for(md, "photos_synthetic", "f-e2")


def test_report_marks_an_unmeasured_blocking_gate_PENDING_never_PASS():
    """A blocking gate whose baseline was not run must not read as a pass (§6a)."""
    recs = [{**rec("f-e2", "rerank", 1), "group": "kept"}]      # ran, produced no metric
    md = rg.report(REPORT_CFG, recs)
    assert "PENDING" in row_for(md, "rerank", "f-e2")
    assert "PASS" not in md
    assert "may ship" not in md


def test_report_lists_a_manual_gate_as_judged_by_a_human():
    md = rg.report(REPORT_CFG, photo_recs(0.99, 0.99, 0.80, 0.80))
    assert "Judged by a human; not run here." in md
    assert "kept/translation_spot_check (manual)" in md
    assert "may ship" not in md                    # it blocks, and it is unmeasured


def test_report_on_no_results_at_all():
    md = rg.report(REPORT_CFG, [])
    assert "- FAIL: 0" in md
    assert "PASS" not in md and "FAIL (blocks" not in md
    assert "kept/rerank/f-e2 (not run)" in md
    assert "kept/rerank/untuned-vision (not run)" in md     # the baseline counts as unmeasured too


def test_report_of_the_real_gate_table_renders_every_gate():
    cfg = rg.load_gates(ROOT / "config" / "gates.yaml")
    md = rg.report(cfg, [])
    for gate in cfg["gates"]:
        assert f"### {gate['id']} " in md
    assert "epoch 1 is NOT the fallback" not in md          # nothing has failed yet


# ───────────────────────── config/gates.yaml ─────────────────────────

def test_every_check_references_a_metric_the_gate_declares():
    for gate in GATES_YAML["gates"]:
        declared = set(gate.get("metrics") or {})
        for chk in gate.get("checks") or []:
            assert chk["metric"] in declared, f"{gate['id']}: check on undeclared metric {chk['metric']}"


def test_every_check_has_a_known_operator_and_one_reference():
    for gate in GATES_YAML["gates"]:
        for chk in gate.get("checks") or []:
            assert chk["op"] in rg.OPS, f"{gate['id']}: unknown op {chk['op']}"
            assert ("value" in chk) != ("vs" in chk), f"{gate['id']}/{chk['metric']}: needs `value` xor `vs`"
            if "vs" in chk:
                assert chk["vs"] == "baseline"
                assert chk["op"] in rg.MARGIN_SIGN, f"{gate['id']}/{chk['metric']}: {chk['op']} needs a constant"


def test_every_gate_group_belongs_to_a_level():
    """A group no level claims would make the gate unrunnable and invisible in the plan."""
    level_groups = {g for lvl in GATES_YAML["levels"].values() for g in lvl.get("groups", [])}
    for gate in GATES_YAML["gates"]:
        assert gate["group"] in level_groups, f"{gate['id']}: no level has the {gate['group']} role"


def test_every_baseline_for_group_is_a_real_group():
    gate_groups = {g["group"] for g in GATES_YAML["gates"]}
    for lid, lvl in GATES_YAML["levels"].items():
        for group in lvl.get("baseline_for", []):
            assert group in gate_groups, f"{lid}: baseline_for unknown group {group}"
            assert group in lvl.get("groups", []), f"{lid}: baseline for {group} it does not run"


def test_each_group_has_at_most_one_baseline_level():
    seen = {}
    for lid, lvl in GATES_YAML["levels"].items():
        for group in lvl.get("baseline_for", []):
            assert group not in seen, f"{group}: two baselines, {seen[group]} and {lid}"
            seen[group] = lid


def test_manual_gates_have_no_command_and_runnable_gates_have_both():
    for gate in GATES_YAML["gates"]:
        if gate.get("manual"):
            assert "cmd" not in gate and "metrics" not in gate, f"{gate['id']}: manual gates are not run"
            assert not gate.get("checks"), f"{gate['id']}: manual gates have no scored checks"
        else:
            assert gate.get("cmd"), f"{gate['id']}: no cmd"
            assert gate.get("metrics"), f"{gate['id']}: no metrics"
            assert gate.get("checks") or gate.get("report_only"), f"{gate['id']}: no checks and not report_only"


def test_gate_ids_are_unique_and_the_placeholders_resolve():
    ids = [g["id"] for g in GATES_YAML["gates"]]
    assert len(ids) == len(set(ids))
    for gate in GATES_YAML["gates"]:
        for arg in gate.get("cmd") or []:
            assert "{" not in arg or arg in ("{label}", "{dump}"), f"{gate['id']}: unknown placeholder {arg}"


def test_the_blocking_gates_are_exactly_the_kept_abilities_of_6a():
    blocking = {g["id"] for g in GATES_YAML["gates"] if g.get("blocking")}
    assert blocking == {"rerank", "figure", "translation_spot_check"}
    assert all(g["group"] == "kept" for g in GATES_YAML["gates"] if g.get("blocking"))
