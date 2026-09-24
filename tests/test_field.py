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
from eval.field.cards import assign, condition_order, load_cards
from eval.field.recorder import create_app
from eval.field.scoring import fact_id, score_clip
from eval.field.stats import bootstrap_f1, cluster_bootstrap_f1, paired_difference, prf
from herald.extraction import ModelExtractor
from tests.fakes import FakeModel

ROOT = Path(__file__).resolve().parent.parent


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


def test_every_card_is_said_before_any_card_is_said_twice():
    ids = [f"fc{i:02d}" for i in range(30)]
    first_three = [c for k in range(3) for c in assign(ids, k, 10)]
    assert sorted(first_three) == ids
    assert assign(ids, 3, 10) == assign(ids, 0, 10)
    assert condition_order(["quiet", "noise"], 0) == ["quiet", "noise"]
    assert condition_order(["quiet", "noise"], 1) == ["noise", "quiet"]


# ---------- recording station ----------
@pytest.fixture
def station(tmp_path):
    cards = write_cards(tmp_path / "cards.jsonl", [card(i) for i in range(1, 13)])
    audio = tmp_path / "audio"
    app = create_app(cards_path=cards, manifest_path=tmp_path / "manifest.jsonl", audio_dir=audio, root=tmp_path)
    return TestClient(app), tmp_path


def post_clip(client, speaker, card_id, condition, raw=None):
    return client.post("/api/clips", data={"speaker": speaker, "card": card_id, "condition": condition},
                       files={"file": ("clip.wav", raw or wav_bytes(), "audio/wav")})


def test_recording_needs_consent_and_gives_a_counterbalanced_plan(station):
    client, _ = station
    assert client.post("/api/speakers", json={"consent": False}).status_code == 400
    s1 = client.post("/api/speakers", json={"consent": True}).json()
    s2 = client.post("/api/speakers", json={"consent": True}).json()
    assert (s1["speaker"], s2["speaker"]) == ("s01", "s02")
    assert len(s1["plan"]) == 20 and s1["plan"][0]["condition"] == "quiet" and s2["plan"][0]["condition"] == "noise"
    assert "facts" not in s1["plan"][0]["card"]                  # the speaker never sees the labels


def test_a_clip_is_saved_as_16k_mono_and_a_redo_replaces_it(station):
    client, tmp = station
    sp = client.post("/api/speakers", json={"consent": True}).json()
    cid = sp["plan"][0]["card"]["id"]
    row = post_clip(client, "s01", cid, "quiet").json()
    assert row["file"] == f"audio/s01/{cid}_quiet.wav" and row["seconds"] == 1.0
    audio, sr = sf.read(tmp / row["file"])
    assert sr == 16000 and audio.ndim == 1
    post_clip(client, "s01", cid, "quiet", wav_bytes(seconds=2.0))
    rows = [json.loads(x) for x in (tmp / "manifest.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["seconds"] == 2.0
    assert client.get(f"/api/speakers/s01/plan").json()["plan"][0]["done"] is True
    assert client.get(f"/api/clips/s01/{cid}/quiet").status_code == 200


def test_bad_clips_are_refused(station):
    client, _ = station
    sp = client.post("/api/speakers", json={"consent": True}).json()
    cid = sp["plan"][0]["card"]["id"]
    assert post_clip(client, "s01", cid, "quiet", wav_bytes(amp=0.001)).status_code == 422      # silent mic
    assert post_clip(client, "s01", cid, "quiet", wav_bytes(seconds=0.2)).status_code == 422    # too short
    assert post_clip(client, "s01", cid, "loud").status_code == 400                             # unknown condition
    assert post_clip(client, "s01", "fc12", "quiet").status_code == 400                         # not this speaker's card
    assert post_clip(client, "s09", cid, "quiet").status_code == 404                            # no consent
    assert post_clip(client, "x", cid, "quiet").status_code == 400                              # not a speaker code
    assert client.post("/api/clips", data={"speaker": "s01", "card": cid, "condition": "quiet"},
                       files={"file": ("clip.wav", b"not audio", "audio/wav")}).status_code == 400


def test_withdrawing_deletes_the_audio_and_every_derived_line(station):
    client, tmp = station
    sp = client.post("/api/speakers", json={"consent": True}).json()
    cid = sp["plan"][0]["card"]["id"]
    post_clip(client, "s01", cid, "quiet")
    (tmp / "audio" / "_transcripts.jsonl").write_text(json.dumps({"speaker": "s01", "text": "woman 72"}) + "\n"
                                                     + json.dumps({"speaker": "s02", "text": "keep"}) + "\n")
    assert client.delete("/api/speakers/s01").json()["clips_deleted"] == 1
    assert not (tmp / "audio" / "s01").exists()
    assert (tmp / "manifest.jsonl").read_text() == ""
    assert "s01" not in (tmp / "audio" / "_transcripts.jsonl").read_text()
    assert client.get("/api/speakers").json() == []
    assert client.post("/api/speakers", json={"consent": True}).json()["speaker"] == "s02"      # codes never reused


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
    p, r, f = prf(10, 2, 4)
    assert round(f, 3) == round(2 * p * r / (p + r), 3)
    lo, hi = bootstrap_f1(units, n=500, seed=1)
    assert (lo, hi) == bootstrap_f1(units, n=500, seed=1) and lo <= 0.769 <= hi
    wide = cluster_bootstrap_f1({"s01": units[:4], "s02": units[4:8]}, n=500)
    assert wide[0] <= wide[1]
    d, dlo, dhi = paired_difference([((3, 0, 0), (2, 0, 1))] * 10, n=200)
    assert d > 0 and dlo <= d <= dhi


# ---------- the benchmark end to end, with fakes ----------
class ScriptedSTT:
    model = "fake-whisper"

    def __init__(self, text: str):
        self.text, self.calls = text, 0

    def transcribe(self, audio, sr, language=None):
        self.calls += 1
        return {"text": self.text, "chunks": [], "seconds": len(audio) / sr}


def test_the_benchmark_scores_clips_through_stt_and_the_extractor(tmp_path):
    cards = load_cards(write_cards(tmp_path / "cards.jsonl", [card(1), card(2, by="other", speaker="husband")]))
    rows = []
    for spk in ("s01", "s02"):
        for cid in ("fc01", "fc02"):
            for cond in ("quiet", "noise"):
                f = tmp_path / spk / f"{cid}_{cond}.wav"
                f.parent.mkdir(exist_ok=True)
                f.write_bytes(wav_bytes())
                rows.append({"speaker": spk, "card": cid, "condition": cond, "file": str(f)})
    (tmp_path / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    clips = field_bench.load_clips(tmp_path / "manifest.jsonl", cards, tmp_path)
    stt = ScriptedSTT("72 year old woman, pressure 188 over 102, she takes Eliquis")
    transcripts = field_bench.transcribe(clips, stt, tmp_path / "_transcripts.jsonl")
    field_bench.transcribe(clips, stt, tmp_path / "_transcripts.jsonl")
    assert stt.calls == 1                         # identical audio: transcribed once, then cached
    model = FakeModel(name="ems-d-fp8", rows=[["patient.age", 72, "m"], ["vitals.sbp", 188, "m"],
                                              ["vitals.dbp", 102, "m"], ["meds.anticoagulant", "apixaban", "m"]])
    preds = field_bench.extract(clips, cards, transcripts, ModelExtractor(model))
    other = preds[("s01", "fc02", "quiet")]["pred"]
    assert {r for _, _, r in other} == {"family"}             # the husband's mic: his words, as the app attributes them
    scores = {field_bench.clip_key(c): score_clip(cards[c["card"]].facts, preds[field_bench.clip_key(c)]["pred"])
              for c in clips}
    res = field_bench.aggregate(clips, scores, ["quiet", "noise"])
    assert res["recall"] < 1.0 and res["precision"] == 1.0    # sex never extracted
    assert set(res["by_condition"]) == {"quiet", "noise"} and res["quiet_minus_noise"]["pairs"] == 4
    assert res["ci95_clips"][0] <= res["f1"] <= res["ci95_clips"][1]
    table = field_bench.per_key_table([scores, scores])
    assert table["patient.sex"]["recall"] == 0.0 and table["vitals.sbp"]["gold_per_run"] == 8.0   # 8 clips a run
