"""Field robustness evaluation (eval/field/, eval/field_bench.py; docs/TASK_SPECS.md S8): cards, the recording
station, per-clip scoring, the statistics, and the benchmark end to end with fakes (no model, no microphone)."""
import io
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from eval import field_bench
from eval.field import manifest as field_manifest
from eval.field.cards import assign, condition_order, load_cards
from eval.field.manifest import ConsentLog, check_speaker, scrub
from eval.field.recorder import create_app
from eval.field.scoring import fact_id, score_clip
from eval.field.stats import bootstrap_f1, cluster_bootstrap_f1, f1, paired_difference
from herald.core.vocabulary import default_vocabulary
from herald.extraction import ModelExtractor
from tests.fakes import FakeModel

ROOT = Path(__file__).resolve().parent.parent
VOCAB = default_vocabulary()


def card(i: int, **over) -> dict:
    d = {"id": f"fc{i:02d}", "call_type": "stroke", "dispatch": "possible stroke", "by": "medic", "speaker": None,
         "say": ["woman, 72", "blood pressure 188 over 102", "takes Eliquis"],
         "facts": [["patient.age", 72, "medic"], ["patient.sex", "F", "medic"], ["vitals.sbp", 188, "medic"],
                   ["vitals.dbp", 102, "medic"], ["meds.anticoagulant", "apixaban", "medic"]]}
    return {**d, **over}


def write_cards(path: Path, cards: list[dict]) -> Path:
    path.write_text("".join(json.dumps(c) + "\n" for c in cards))
    return path


def wav_bytes(seconds=1.0, sr=48000, amp=0.3) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    buf = io.BytesIO()
    sf.write(buf, (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ---------- cards ----------
def test_the_committed_cards_validate_against_the_vocabulary():
    cards = load_cards(ROOT / "eval" / "field_cards_v1.jsonl")
    assert len(cards) == 30
    assert {c.by.value for c in cards.values()} == {"medic", "other"}


@pytest.mark.parametrize("bad, why", [
    (card(1, facts=[["vitals.shoe_size", 9, "medic"]]), "unknown key"),
    (card(1, facts=[["vitals.spo2", 400, "medic"]]), "implausible"),
    (card(1, facts=[["patient.age", 72, "doctor"]]), "role"),
    (card(1, by="other"), "names who is speaking"),
    (card(1, speaker="wife"), "no speaker label"),
    (card(1, say=["too", "short"]), "say needs"),
    (card(1, facts=[]), "no facts"),
])
def test_bad_cards_are_rejected_with_the_reason(tmp_path, bad, why):
    with pytest.raises(ValueError, match=why):
        load_cards(write_cards(tmp_path / "c.jsonl", [bad]))


def test_duplicate_card_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_cards(write_cards(tmp_path / "c.jsonl", [card(1), card(1)]))


def test_card_facts_are_stored_in_the_vocabularys_normalized_form(tmp_path):
    cards = load_cards(write_cards(tmp_path / "c.jsonl", [card(1, facts=[
        ["allergies", "none", "medic"], ["ecg.attached", "yes", "medic"], ["patient.age", "72", "medic"]])]))
    assert cards["fc01"].facts == (("allergies", [], "medic"), ("ecg.attached", True, "medic"),
                                   ("patient.age", 72, "medic"))
    # the model's canonical [] for "no allergies" is a hit, not a miss plus a false positive
    assert score_clip(cards["fc01"].facts, [("allergies", [], "medic"), ("ecg.attached", True, "medic"),
                                            ("patient.age", 72, "medic")]).all_keys[:3] == [3, 0, 0]


def test_every_card_is_said_before_any_card_is_said_twice():
    ids = [f"fc{i:02d}" for i in range(30)]
    first_three = [c for k in range(3) for c in assign(ids, k, 10)]
    assert sorted(first_three) == ids
    assert assign(ids, 3, 10) == assign(ids, 0, 10)
    assert condition_order(["quiet", "noise"], 0) == ["quiet", "noise"]      # first speaker: quiet first
    assert condition_order(["quiet", "noise"], 1) == ["noise", "quiet"]
    # six slots cover every block in both orders
    assert {(assign(ids, k, 10)[0], condition_order(["q", "n"], k)[0]) for k in range(6)} == \
        {(b, o) for b in ("fc00", "fc10", "fc20") for o in ("q", "n")}


# ---------- recording station ----------
@pytest.fixture
def paths(tmp_path):
    return {"cards_path": write_cards(tmp_path / "cards.jsonl", [card(i) for i in range(1, 31)]),
            "manifest_path": tmp_path / "manifest.jsonl", "audio_dir": tmp_path / "audio"}


@pytest.fixture
def station(paths, tmp_path):
    return TestClient(create_app("test", **paths)), tmp_path


def post_clip(client, speaker, card_id, condition, raw=None):
    return client.post("/api/clips", data={"speaker": speaker, "card": card_id, "condition": condition},
                       files={"file": ("clip.wav", raw or wav_bytes(), "audio/wav")})


def test_recording_needs_consent_and_gives_a_counterbalanced_plan(station):
    client, _ = station
    assert client.post("/api/speakers", json={"consent": False}).status_code == 400
    s1 = client.post("/api/speakers", json={"consent": True}).json()
    s2 = client.post("/api/speakers", json={"consent": True}).json()
    assert (s1["speaker"], s2["speaker"]) == ("test-s01", "test-s02")
    assert len(s1["plan"]) == 20 and s1["plan"][0]["condition"] == "quiet" and s2["plan"][0]["condition"] == "noise"
    assert "facts" not in s1["plan"][0]["card"]                  # the speaker never sees the labels
    assert client.get("/api/protocol").json()["station"] == "test"


def test_stations_sharing_the_audio_folder_get_distinct_codes_and_one_global_rotation(paths):
    a, b = TestClient(create_app("ana", **paths)), TestClient(create_app("ben", **paths))
    sa = a.post("/api/speakers", json={"consent": True}).json()
    sb = b.post("/api/speakers", json={"consent": True}).json()
    assert (sa["speaker"], sb["speaker"]) == ("ana-s01", "ben-s01")
    assert sb["plan"][0]["card"]["id"] == "fc11" and sb["plan"][0]["condition"] == "noise"    # the next slot
    assert [s["speaker"] for s in a.get("/api/speakers").json()] == ["ana-s01"]               # each lists its own
    assert b.get("/api/speakers/ana-s01/plan").status_code == 403                             # and touches only them
    assert b.delete("/api/speakers/ana-s01").status_code == 403


def test_a_withdrawn_speakers_slot_goes_to_the_next_person_but_the_code_is_never_reused(station):
    client, _ = station
    for _ in range(2):
        client.post("/api/speakers", json={"consent": True})
    client.delete("/api/speakers/test-s01")
    s3 = client.post("/api/speakers", json={"consent": True}).json()
    assert s3["speaker"] == "test-s03" and s3["slot"] == 0 and s3["plan"][0]["card"]["id"] == "fc01"


def test_speaker_codes_past_99_still_work():
    assert check_speaker("jenil-s100") == "jenil-s100"
    for bad in ("s01", "jenil-01", "Jenil-s01", "../s01", "jenil-s1"):
        with pytest.raises(ValueError):
            check_speaker(bad)


def test_a_clip_is_saved_as_16k_mono_and_a_redo_replaces_it(station):
    client, tmp = station
    sp = client.post("/api/speakers", json={"consent": True}).json()
    cid = sp["plan"][0]["card"]["id"]
    row = post_clip(client, "test-s01", cid, "quiet").json()
    assert row["file"] == f"test-s01/{cid}_quiet.wav" and row["seconds"] == 1.0          # relative to the audio folder
    audio, sr = sf.read(tmp / "audio" / row["file"])
    assert sr == 16000 and audio.ndim == 1
    post_clip(client, "test-s01", cid, "quiet", wav_bytes(seconds=2.0))
    rows = [json.loads(x) for x in (tmp / "manifest.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["seconds"] == 2.0
    assert client.get("/api/speakers/test-s01/plan").json()["plan"][0]["done"] is True
    assert client.get(f"/api/clips/test-s01/{cid}/quiet").status_code == 200


def test_bad_clips_are_refused(station):
    client, _ = station
    sp = client.post("/api/speakers", json={"consent": True}).json()
    cid = sp["plan"][0]["card"]["id"]
    assert post_clip(client, "test-s01", cid, "quiet", wav_bytes(amp=0.001)).status_code == 422      # silent mic
    assert post_clip(client, "test-s01", cid, "quiet", wav_bytes(seconds=0.2)).status_code == 422    # too short
    assert post_clip(client, "test-s01", cid, "loud").status_code == 400                             # unknown condition
    assert post_clip(client, "test-s01", "fc12", "quiet").status_code == 400                         # not their card
    assert post_clip(client, "test-s09", cid, "quiet").status_code == 404                            # no consent
    assert post_clip(client, "x", cid, "quiet").status_code == 400                                   # not a code
    assert client.post("/api/clips", data={"speaker": "test-s01", "card": cid, "condition": "quiet"},
                       files={"file": ("clip.wav", b"not audio", "audio/wav")}).status_code == 400


def test_withdrawing_deletes_the_audio_and_every_derived_line(station):
    client, tmp = station
    sp = client.post("/api/speakers", json={"consent": True}).json()
    cid = sp["plan"][0]["card"]["id"]
    post_clip(client, "test-s01", cid, "quiet")
    audio = tmp / "audio"
    (audio / "_transcripts.jsonl").write_text(json.dumps({"speaker": "test-s01", "text": "woman 72"}) + "\n"
                                              + json.dumps({"speaker": "test-s02", "text": "keep"}) + "\n")
    (audio / "_bench").mkdir()
    (audio / "_bench" / "omissions.jsonl").write_text(          # hand-edited: a broken line of each speaker
        '{"speaker": "test-s01", "omitted": [\n{"speaker": "test-s02", "omitted": [\n\n')
    assert client.delete("/api/speakers/test-s01").json()["clips_deleted"] == 1
    assert not (audio / "test-s01").exists()
    assert (tmp / "manifest.jsonl").read_text() == ""
    assert "test-s01" not in (audio / "_transcripts.jsonl").read_text()
    left = (audio / "_bench" / "omissions.jsonl").read_text()
    assert "test-s01" not in left and "test-s02" in left          # unparseable lines: dropped only if they name the code
    assert client.get("/api/speakers").json() == []
    assert client.post("/api/speakers", json={"consent": True}).json()["speaker"] == "test-s02"   # never reused


@pytest.mark.parametrize("broken_rmtree", [
    lambda path: (_ for _ in ()).throw(PermissionError("busy")),     # the delete fails
    lambda path: None,                                                # the delete "succeeds" but the folder stays
])
def test_a_failed_delete_is_reported_and_nothing_is_marked_withdrawn(station, monkeypatch, broken_rmtree):
    client, tmp = station
    cid = client.post("/api/speakers", json={"consent": True}).json()["plan"][0]["card"]["id"]
    post_clip(client, "test-s01", cid, "quiet")
    monkeypatch.setattr(field_manifest.shutil, "rmtree", broken_rmtree)
    r = client.delete("/api/speakers/test-s01")
    assert r.status_code == 500 and "nothing was marked withdrawn" in r.json()["detail"]
    assert [s["speaker"] for s in client.get("/api/speakers").json()] == ["test-s01"]         # still listed: retry
    assert not any(e["event"] == "withdrawn" for e in ConsentLog(tmp / "audio").entries())
    monkeypatch.undo()
    assert client.delete("/api/speakers/test-s01").status_code == 200                         # the retry works
    assert not (tmp / "audio" / "test-s01").exists()


def test_scrub_keeps_other_speakers_lines(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"speaker": "a-s01"}\n{"speaker": "a-s010"}\nnot json\n')
    assert scrub(p, "a-s01") == 1 and p.read_text() == '{"speaker": "a-s010"}\nnot json\n'


def test_the_station_serves_the_apps_own_capture_code(station):
    client, _ = station
    js = client.get("/wav.js")
    assert js.status_code == 200 and "function encodeWav" in js.text
    assert js.text == (ROOT / "web" / "wav.js").read_text()
    page = client.get("/").text
    assert 'src="/wav.js"' in page and "function encodeWav" not in page       # not a copy


# ---------- scoring and statistics ----------
def test_a_clip_is_scored_with_the_benchmarks_atoms():
    gold = [("patient.age", 72, "medic"), ("meds.list", ["apixaban", "metformin"], "medic"),
            ("meds.given", {"drug": "aspirin", "dose": 324, "unit": "mg"}, "medic"),
            ("complaint.chief", "left sided weakness", "medic")]
    pred = [("patient.age", 72, "medic"), ("meds.list", ["apixaban"], "family"),
            ("meds.given", {"drug": "aspirin", "dose": 324}, "medic"), ("complaint.chief", "weak on the left", "medic"),
            ("vitals.hr", 90, "medic")]
    s = score_clip(gold, pred)
    assert s.headline[:3] == [2, 1, 1]           # age + apixaban right, HR extra, metformin missed (records, free text: groups)
    assert s.headline[3] == 1                     # apixaban credited to family: role wrong
    assert s.per_key["meds.given"] == [2, 0, 1]   # drug and dose right, unit missed
    assert s.per_key["complaint.chief"] == [1, 0, 0]              # free text by presence
    assert [f[:2] for f in s.missed_facts] == [["meds.list", ["metformin"]],
                                               ["meds.given", {"drug": "aspirin", "dose": 324, "unit": "mg"}]]
    said = score_clip(gold, pred, omitted={fact_id("meds.list", ["metformin"])})    # the speaker never said it
    assert said.headline[:3] == [2, 1, 0]         # apixaban still counts; only the unsaid item leaves the gold


def test_intervals_are_reproducible_and_cover_the_point():
    units = [(3, 0, 1), (2, 1, 1), (4, 0, 0), (1, 1, 2)] * 5
    assert round(f1([(10, 2, 4)]), 3) == round(2 * (10 / 12) * (10 / 14) / (10 / 12 + 10 / 14), 3)
    lo, hi = bootstrap_f1(units, n=500, seed=1)
    assert (lo, hi) == bootstrap_f1(units, n=500, seed=1) and lo <= 0.769 <= hi
    wide = cluster_bootstrap_f1({"s01": units[:4], "s02": units[4:8]}, n=500)
    assert wide[0] <= wide[1]


def test_the_noise_difference_is_resampled_by_speaker():
    """One speaker with a big noise effect and four with none: as independent pairs the difference looks certain;
    by speaker the interval reaches zero, because a sample without that speaker is 1 draw in 3."""
    same = [((3, 0, 0), (3, 0, 0))] * 10
    groups = {"a-s01": [((3, 0, 0), (0, 0, 3))] * 10, **{f"a-s0{i}": same for i in range(2, 6)}}
    d, lo, hi = paired_difference(groups, n=1000)
    assert d > 0.1 and lo <= 0.0 < hi
    naive = {f"pair{i}": [p] for i, p in enumerate(p for g in groups.values() for p in g)}   # every pair its own unit
    assert paired_difference(naive, n=1000)[1] > 0.0


# ---------- the benchmark end to end, with fakes ----------
class ScriptedSTT:
    model = "fake-whisper"

    def __init__(self, text: str, prompt: str = "EMS vocabulary"):
        self.text, self.prompt, self.calls = text, prompt, 0

    def transcribe(self, audio, sr, language=None):
        self.calls += 1
        return {"text": self.text, "chunks": [], "seconds": len(audio) / sr}


ANSWER = [["patient.age", 72, "m"], ["vitals.sbp", 188, "m"], ["vitals.dbp", 102, "m"],
          ["meds.anticoagulant", "apixaban", "m"]]


def record(tmp_path) -> tuple[dict, Path, Path]:
    """Two cards (one on the husband's mic), two speakers, both conditions; identical audio everywhere."""
    cards = load_cards(write_cards(tmp_path / "cards.jsonl", [card(1), card(2, by="other", speaker="husband")]))
    audio, rows = tmp_path / "audio", []
    for spk in ("tt-s01", "tt-s02"):
        for cid in ("fc01", "fc02"):
            for cond in ("quiet", "noise"):
                f = audio / spk / f"{cid}_{cond}.wav"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(wav_bytes())
                rows.append({"speaker": spk, "card": cid, "condition": cond, "file": f"{spk}/{f.name}"})
    (tmp_path / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return cards, tmp_path / "manifest.jsonl", audio


def test_the_benchmark_scores_clips_through_stt_and_the_extractor(tmp_path):
    cards, manifest, audio = record(tmp_path)
    clips = field_bench.load_clips(manifest, cards, audio)
    stt = ScriptedSTT("72 year old woman, pressure 188 over 102, she takes Eliquis")
    transcripts = field_bench.transcribe(clips, stt, tmp_path / "_transcripts.jsonl")
    field_bench.transcribe(clips, stt, tmp_path / "_transcripts.jsonl")
    assert stt.calls == 1                         # identical audio: transcribed once, then cached
    preds = field_bench.extract(clips, cards, transcripts, ModelExtractor(FakeModel(name="ems-e-fp8", rows=ANSWER)))
    other = preds[("tt-s01", "fc02", "quiet")]["pred"]
    assert {r for _, _, r in other} == {"family"}             # the husband's mic: his words, as the app attributes them
    scores = {field_bench.clip_key(c): score_clip(cards[c["card"]].facts, preds[field_bench.clip_key(c)]["pred"])
              for c in clips}
    res = field_bench.aggregate(clips, scores, ["quiet", "noise"])
    assert res["recall"] < 1.0 and res["precision"] == 1.0    # sex never extracted
    assert set(res["by_condition"]) == {"quiet", "noise"}
    assert res["quiet_minus_noise"]["pairs"] == 4 and res["quiet_minus_noise"]["speakers"] == 2
    assert res["ci95_clips"][0] <= res["f1"] <= res["ci95_clips"][1]
    table = field_bench.per_key_table([scores, scores])
    assert table["patient.sex"]["recall"] == 0.0 and table["vitals.sbp"]["gold_per_run"] == 8.0   # 8 clips a run


def test_a_new_whisper_prompt_invalidates_the_transcript_cache(tmp_path):
    cards, manifest, audio = record(tmp_path)
    clips = field_bench.load_clips(manifest, cards, audio)
    field_bench.transcribe(clips, ScriptedSTT("old"), tmp_path / "c.jsonl")
    fresh = ScriptedSTT("new", prompt="a different priming prompt")
    assert field_bench.transcribe(clips, fresh, tmp_path / "c.jsonl")[("tt-s01", "fc01", "quiet")]["text"] == "new"
    assert fresh.calls == 1


def test_clips_of_a_withdrawn_speaker_are_never_scored(tmp_path):
    cards, manifest, audio = record(tmp_path)
    (audio / "consent.jsonl").write_text(json.dumps({"event": "withdrawn", "speaker": "tt-s02", "at": "x"}) + "\n")
    with pytest.raises(SystemExit, match="withdrew: tt-s02"):
        field_bench.load_clips(manifest, cards, audio)


def test_the_review_sheet_lists_every_card_fact_with_the_audio_and_no_model_output(tmp_path):
    cards, manifest, audio = record(tmp_path)
    clips = field_bench.load_clips(manifest, cards, audio)
    sheet = field_bench.review_sheet(clips, cards)
    assert len(sheet) == 8
    assert sheet[0]["audio"] == str(audio / "tt-s01" / "fc01_quiet.wav") and sheet[0]["say"] == list(cards["fc01"].say)
    assert sheet[0]["facts"] == [list(f) for f in cards["fc01"].facts] and sheet[0]["omitted"] == []
    assert not {"transcript", "pred", "missed", "missed_facts"} & set(sheet[0])


def test_omissions_tolerate_blank_lines_normalize_values_and_warn_on_typos(tmp_path):
    cards, manifest, audio = record(tmp_path)
    clips = field_bench.load_clips(manifest, cards, audio)
    path = tmp_path / "omissions.jsonl"
    path.write_text(json.dumps({"speaker": "tt-s01", "card": "fc01", "condition": "quiet",
                                "omitted": [["patient.age", 72.0, "medic"], ["patient.age", 27, "medic"]]})
                    + "\n\n" + json.dumps({"speaker": "tt-s09", "card": "fc01", "condition": "quiet",
                                           "omitted": [["patient.sex", "F", "medic"]]}) + "\n\n")
    omitted, warnings = field_bench.load_omissions(path, clips, cards, VOCAB)
    assert omitted == {("tt-s01", "fc01", "quiet"): {fact_id("patient.age", 72)}}      # 72.0 is the card's 72
    assert len(warnings) == 2 and "matches no fact" in warnings[0] and "not a clip" in warnings[1]


def test_the_benchmark_never_overwrites_the_reviewed_sheet(tmp_path, monkeypatch):
    import eval.bench_extract
    import herald.models.stt
    cards_path = write_cards(tmp_path / "cards.jsonl", [card(1), card(2, by="other", speaker="husband")])
    _, manifest, audio = record(tmp_path)
    monkeypatch.setattr(herald.models.stt, "WhisperSTT", lambda *a, **k: ScriptedSTT("woman 72, 188 over 102"))
    model = FakeModel(name="ems-e-fp8", rows=ANSWER)
    monkeypatch.setattr(eval.bench_extract, "build_extractor", lambda kind, m: (None, ModelExtractor(model), model))
    args = ["--cards", str(cards_path), "--manifest", str(manifest), "--audio-dir", str(audio), "--runs", "1",
            "--out", str(tmp_path / "results.jsonl"), "--summary-dir", str(tmp_path / "summary")]
    field_bench.main(args)
    sheet = audio / "_bench" / "omissions_review.jsonl"
    rows = [json.loads(x) for x in sheet.read_text().splitlines()]
    rows[0]["omitted"] = [["patient.sex", "F", "medic"]]              # the reviewer edits the sheet in place
    sheet.write_text("".join(json.dumps(r) + "\n" for r in rows))
    edited = sheet.read_text()
    field_bench.main(args + ["--omissions", str(sheet)])
    assert sheet.read_text() == edited
    last = json.loads((tmp_path / "results.jsonl").read_text().splitlines()[-1])
    assert last["said"]["facts_omitted"] == 1 and last["said"]["recall"] > last["recall"]
    assert set(last["inputs"]) == {"cards", "stt", "omissions"} and last["latency_ms_p95"] >= last["latency_ms_p50"]
