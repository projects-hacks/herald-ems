"""Training-set builder (scripts/build_train_set.py, scripts/train_data.py): decontamination, drug relabels, overlays,
the neutral chat record, and the run F profile (MODEL_PLAN §0k)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from herald.config import get_settings
from herald.core.schema import CapturedBy
from herald.extraction.profiles import Profiles
from scripts.train_data import (Decontaminator, DrugRelabel, chat_messages, expand, held_out_texts,
                                merge_overlay)

ROOT = Path(__file__).resolve().parent.parent
RELABEL = ROOT / "data" / "annotated" / "drug_relabel_f.yaml"


def test_an_eight_word_run_or_the_same_words_count_as_overlap():
    d = Decontaminator(["BP one forty over ninety, pulse eighty eight, sats ninety six on room air.",
                        "Mark her as DNR."])
    assert d.overlaps("so uh pulse eighty eight, sats ninety six on room air and she's alert")   # shared 8-word run
    assert d.overlaps("mark her as dnr")                        # short item: same words, other case/punctuation
    assert not d.overlaps("mark her as DNR please")             # a short item is matched whole, not by prefix
    assert not d.overlaps("pulse eighty eight, sats ninety six")                                  # 6 words only


def test_held_out_texts_read_gold_adversarial_and_scenarios(tmp_path):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({"id": "g1", "text": "alpha"}) + "\n" + json.dumps({"id": "g2", "broad": []}) + "\n")
    cards = tmp_path / "cards.jsonl"
    cards.write_text(json.dumps({"id": "c1", "say": ["woman, 72", "left face droop"]}) + "\n")
    scen = tmp_path / "demo.json"
    scen.write_text(json.dumps({"steps": [{"incident": "fall"}, {"say": "Glucose 142."}, {"confirm": "x"}]}))
    assert held_out_texts(gold) == ["alpha"]                    # label-only lines are skipped, not an error
    assert held_out_texts(cards) == ["woman, 72", "left face droop", "woman, 72 left face droop"]
    assert held_out_texts(scen) == ["Glucose 142."]
    assert expand(f"{tmp_path}/*.jsonl,{scen}") == sorted([str(cards), str(gold)]) + [str(scen)]
    with pytest.raises(FileNotFoundError):
        expand(f"{tmp_path}/nothing_*.jsonl")


def test_drug_relabel_renames_list_items_plain_values_and_one_record_field():
    r = DrugRelabel([{"key": "meds.list", "before": "divalproex", "after": "valproate"},
                     {"key": "meds.given", "field": "drug", "before": "normal saline", "after": "sodium chloride"}])
    assert r.fact(["meds.list", ["divalproex", "metformin"], "medic"]) == ["meds.list", ["valproate", "metformin"], "medic"]
    assert r.fact(["meds.given", {"drug": "normal saline", "dose": 500}, "medic", None]) == \
        ["meds.given", {"drug": "sodium chloride", "dose": 500}, "medic", None]
    assert r.fact(["allergies", ["divalproex"], "medic"]) == ["allergies", ["divalproex"], "medic"]   # other key
    assert sum(r.applied.values()) == 2


def test_overlay_adds_facts_keeps_repeats_and_extends_a_record_in_place():
    facts = [["meds.given", {"drug": "naloxone", "by": "fire"}, "medic", None], ["patient.age", 40, "medic", None]]
    out = merge_overlay(facts, [["patient.age", 40, "medic", None],                     # already there: skipped
                                ["meds.given", {"drug": "naloxone", "by": "fire", "before_arrival": True},
                                 "medic", None],                                        # extends the record
                                ["airway.status", "patent", "medic", None]])
    assert out == [["meds.given", {"drug": "naloxone", "by": "fire", "before_arrival": True}, "medic", None],
                   ["patient.age", 40, "medic", None], ["airway.status", "patent", "medic", None]]
    twice = [["meds.given", {"drug": "albuterol"}, "family", "father"]] * 2
    assert merge_overlay([], twice) == twice                     # a dose said twice stays two (collapsed to a count)


def test_chat_record_is_system_user_assistant():
    m = chat_messages("SYS", "[dispatch: fall]\n[paramedic speaking]\nBP 120", '{"f":[]}')
    assert [x["role"] for x in m] == ["system", "user", "assistant"]
    assert all(isinstance(x["content"], str) for x in m)


def test_run_f_profile_sends_exactly_run_e_input():
    p = Profiles.from_config()
    f, e = p.for_label("herald-f"), p.for_label("ems-e-v2-fp8")
    assert f is not e and f.label_prefix == "herald-f" and p.for_label("herald-f-fp8") is f
    assert f.prompt == e.prompt                                  # "the prompt stays"
    for args in [("She fell", CapturedBy.medic, None, "fall"), ("Mom is allergic", CapturedBy.other, "daughter", None)]:
        assert p.model_input(f, *args) == p.model_input(e, *args)


def test_relabel_list_is_well_formed():
    entries = yaml.safe_load(RELABEL.read_text())["relabel"]
    assert entries and len({(e["key"], e.get("field"), e["before"]) for e in entries}) == len(entries)
    for e in entries:
        assert e["before"] != e["after"] and e["after"] == e["after"].lower() and e["count"] >= 1


INDEX = get_settings().terminology_index


@pytest.mark.skipif(not INDEX.exists(), reason="RxNorm index not built (scripts/build_rxnorm_index.py)")
def test_every_relabel_target_codes_to_itself_exactly():
    from herald.terminology.rxnorm import RxNormNormalizer
    n = RxNormNormalizer.load(INDEX)
    for e in yaml.safe_load(RELABEL.read_text())["relabel"]:
        r = n.normalize(e["key"], e["after"])
        assert (r.method, r.value) == ("exact", e["after"]), e
        b = n.normalize(e["key"], e["before"])
        assert not (b.method == "exact" and b.value == e["before"]), e      # the old spelling really needed it


def test_builder_end_to_end_with_relabel_decontamination_and_chat(tmp_path):
    ann = tmp_path / "annotated"
    ann.mkdir()
    rows = [{"id": "t1", "dispatch": "seizure", "text": "takes divalproex, NKDA", "by": "medic", "speaker": None,
             "facts": [["meds.list", ["divalproex"], "medic", None], ["allergies", [], "medic", None]]},
            {"id": "t2", "dispatch": "", "text": "Mark her as DNR.", "by": "medic", "speaker": None, "facts": []},
            {"id": "t3", "dispatch": "fall", "text": "fire gave narcan before we got there", "by": "medic",
             "speaker": None, "facts": [["meds.given", {"drug": "naloxone", "by": "fire"}, "medic", None]]}]
    (ann / "batch_01.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (ann / "runf_labels_b01.jsonl").write_text(json.dumps(
        {"id": "t3", "runf": [["meds.given", {"drug": "naloxone", "by": "fire", "before_arrival": True},
                               "medic", None]]}) + "\n")
    gold = tmp_path / "adv.jsonl"
    gold.write_text(json.dumps({"id": "a1", "text": "mark her as DNR"}) + "\n")
    out = tmp_path / "out"
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_train_set.py"), "--annotated", str(ann),
                          "--composed", "0", "--dev-frac", "0", "--out", str(out), "--order", "spoken",
                          "--profile", "herald-f", "--overlays", "runf", "--relabel", str(RELABEL),
                          "--decontaminate", str(gold), "--chat"], capture_output=True, text=True, check=True)
    report = json.loads(res.stdout)
    assert report["decontaminated_ids"] == ["t2"]
    train = {r["id"]: r for r in map(json.loads, (out / "train.jsonl").read_text().splitlines())}
    assert set(train) == {"t1", "t3"}
    assert json.loads(train["t1"]["completion"])["f"][0] == ["meds.list", ["valproate"], "m"]
    assert json.loads(train["t3"]["completion"])["f"] == [
        ["meds.given", {"drug": "naloxone", "by": "fire", "before_arrival": True}, "m"]]
    m = train["t1"]["messages"]
    assert m[1]["content"] == train["t1"]["text"] == "[dispatch: seizure]\n[paramedic speaking]\ntakes divalproex, NKDA"
    assert m[2]["content"] == train["t1"]["completion"] and m[0]["content"].startswith("Extract EMS facts")


def _build(ann, out, *extra):
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_train_set.py"), "--annotated", str(ann),
                          "--composed", "0", "--out", str(out), "--order", "spoken", "--profile", "herald-f",
                          "--overlays", "", "--dispatch", "--chat", *extra], capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def test_asr_flag_adds_kept_transcripts_to_train_only_and_leaves_every_other_row_byte_identical(tmp_path):
    ann = tmp_path / "annotated"
    ann.mkdir()
    rows = [{"id": f"t{i}", "dispatch": "fall", "text": f"line {i}: on apixaban, pulse {80 + i}, patient number {i}",
             "by": "medic", "speaker": None,
             "facts": [["meds.list", ["apixaban"], "medic", None], ["vitals.hr", 80 + i, "medic", None]]}
            for i in range(10)]
    (ann / "batch_01.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    held = tmp_path / "held.jsonl"
    held.write_text(json.dumps({"text": "a held out line that must never be trained on ever"}) + "\n")
    plain = _build(ann, tmp_path / "plain", "--decontaminate", str(held))
    base_train = (tmp_path / "plain" / "train.jsonl").read_text().splitlines()
    base_dev = (tmp_path / "plain" / "dev.jsonl").read_text()
    train_ids = [json.loads(l)["id"] for l in base_train]
    dev_id = json.loads(base_dev.splitlines()[0])["id"]
    raw = {r["id"]: r["text"] for r in rows}
    a, b, c, d = train_ids[:4]
    asr = [
        {"clip": "0001", "source_id": a, "raw_text": raw[a], "condition": "snr8", "kept": True, "reason": "kept",
         "whisper": raw[a].replace("apixaban", "a pixaban")},
        {"clip": "0002", "source_id": b, "raw_text": raw[b], "condition": "snr3", "kept": False,
         "reason": "number lost: vitals.hr", "whisper": "line on a pixaban"},
        {"clip": "0003", "source_id": dev_id, "raw_text": raw[dev_id], "condition": "clean", "kept": True,
         "reason": "kept", "whisper": raw[dev_id].upper()},
        {"clip": "0004", "source_id": c, "raw_text": raw[c], "condition": "clean", "kept": True, "reason": "kept",
         "whisper": raw[c]},
        {"clip": "0005", "source_id": d, "raw_text": raw[d], "condition": "snr15", "kept": True, "reason": "kept",
         "whisper": "A held out line that must never be trained on, ever."},
        {"clip": "0006", "source_id": b, "raw_text": "an older text of the line", "condition": "snr15",
         "kept": True, "reason": "kept", "whisper": "an older text of the line"},
    ]
    e = train_ids[4]
    asr.append({"clip": "0007", "source_id": "c999", "raw_text": raw[e], "condition": "snr3", "kept": True,
                "reason": "kept", "whisper": raw[e].replace("pulse", "pulls")})               # id moved: found by text
    f = train_ids[5]
    asr.append({"clip": "0008", "source_id": f, "raw_text": raw[f], "condition": "snr3", "kept": True,
                "reason": "kept", "whisper": raw[f].replace(f"pulse {80 + int(f[1:])}", "pulse")})  # judged before a
    asr_file = tmp_path / "asr.jsonl"
    asr_file.write_text("".join(json.dumps(x) + "\n" for x in asr))
    report = _build(ann, tmp_path / "asr", "--decontaminate", str(held), "--asr", str(asr_file))

    assert (tmp_path / "asr" / "dev.jsonl").read_text() == base_dev                       # dev stays clean text
    train = (tmp_path / "asr" / "train.jsonl").read_text().splitlines()
    assert [l for l in train if json.loads(l)["source"] != "asr"] == base_train          # byte-identical, same order
    added = [json.loads(l) for l in train if json.loads(l)["source"] == "asr"]
    assert sorted(r["id"] for r in added) == sorted([f"{a}~asr0001", f"{e}~asr0007"])
    src = next(json.loads(l) for l in base_train if json.loads(l)["id"] == a)
    r = next(r for r in added if r["id"] == f"{a}~asr0001")
    assert r["raw_text"] == raw[a].replace("apixaban", "a pixaban")
    assert r["completion"] == src["completion"]                                           # the clean labels
    assert r["dispatch"] == src["dispatch"] and r["speaker"] == src["speaker"] and r["by"] == src["by"]
    assert r["text"] == src["text"].replace("apixaban", "a pixaban")                     # same dispatch/speaker lines
    assert [m["content"] for m in r["messages"]][1:] == [r["text"], r["completion"]]
    assert report["asr"] == 2 and report["train"] == plain["train"] + 2
    assert report["asr_counts"] == {
        "asr added: snr8": 1, "asr added: snr3": 1, "asr judged out: number lost": 1,
        "asr: source line not in train (in dev, or no longer built)": 2,
        "asr: transcript identical to the clean line": 1,
        "asr: overlaps a held-out set (8-word run or same words)": 1,
        "asr: labels no longer supported (grounding lost)": 1}
