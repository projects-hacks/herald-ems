"""The 'Herald thinking' trace records what each capture actually did, in two phases:
rules immediately, then the model's additions on the same entry."""
import os
import time

os.environ["HERALD_WARM_STT"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from herald import app as app_mod  # noqa: E402
from herald import extract_llm, llm  # noqa: E402
from herald.schema import CapturedBy, FactIn, Provenance, Role  # noqa: E402


def _client(monkeypatch, model_facts=None, fail=False):
    monkeypatch.setattr(app_mod.RELAY, "ed_url", None)
    if model_facts is None and not fail:
        monkeypatch.setattr(llm, "available", lambda: False)
    else:
        monkeypatch.setattr(llm, "available", lambda: True)
        monkeypatch.setattr(llm, "model_name", lambda: "test-model")

        def fake(text, captured_by, default_role, speaker, audio_id):
            if fail:
                raise RuntimeError("model down")
            extract_llm.extract.last_usage = {"completion_tokens": 42}
            return model_facts
        monkeypatch.setattr(extract_llm, "extract", fake)
    return TestClient(app_mod.app)


def _wait_model(c, status_not="running", timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        tr = c.get("/api/state").json()["transcripts"][-1]["trace"]
        if tr["model"]["status"] != status_not:
            return tr
        time.sleep(0.05)
    raise AssertionError("model phase did not finish")


def test_rules_only_trace_records_effects(monkeypatch):
    with _client(monkeypatch) as c:
        c.post("/api/incident", json={"dispatch": "possible stroke"})
        r = c.post("/api/transcript", json={"text": "She takes warfarin. Glucose 142.", "use_llm": True}).json()
        tr = r["transcript"]["trace"]
        assert tr["model"]["status"] == "off"
        keys = {f["key"] for f in tr["rules"]["facts"]}
        assert {"meds.anticoagulant", "vitals.glucose"} <= keys
        stroke = next(x for x in tr["effects"]["readiness"] if x["label"] == "Stroke alert")
        assert stroke["to"] == stroke["from"] + 2
        assert "meds.anticoagulant" in tr["effects"]["gaps_closed"]
        warf = next(f for f in tr["rules"]["facts"] if f["key"] == "meds.anticoagulant")
        assert warf["relay"].startswith("eligible")


def test_model_phase_updates_same_entry_and_model_only_facts_need_confirmation(monkeypatch):
    extra = [FactIn(key="stroke.onset_witnessed", value=True, role=Role.family, speaker="husband",
                    captured_by=CapturedBy.medic, confidence=0.9, provenance=Provenance(extractor="llm:test"))]
    with _client(monkeypatch, model_facts=extra) as c:
        c.post("/api/incident", json={"dispatch": "possible stroke"})
        r = c.post("/api/transcript", json={"text": "Husband saw it happen.", "use_llm": True}).json()
        assert r["transcript"]["trace"]["model"]["status"] == "running"
        tr = _wait_model(c)
        assert tr["model"]["status"] == "done" and tr["model"]["tokens"] == 42
        [f] = tr["model"]["facts"]
        assert f["key"] == "stroke.onset_witnessed" and f["status"] == "unconfirmed"
        assert f["relay"].startswith("held")
        assert len(c.get("/api/state").json()["transcripts"]) == 1      # updated in place, not a new card


def test_model_error_is_recorded_not_fatal(monkeypatch):
    with _client(monkeypatch, fail=True) as c:
        c.post("/api/incident", json={"dispatch": "possible stroke"})
        c.post("/api/transcript", json={"text": "Glucose 142.", "use_llm": True})
        tr = _wait_model(c)
        assert tr["model"]["status"] == "error" and "model down" in tr["model"]["error"]
        assert any(f["key"] == "vitals.glucose" for f in tr["rules"]["facts"])


def test_implausible_rules_fact_is_listed_as_rejected(monkeypatch):
    c = _client(monkeypatch)
    c.post("/api/incident", json={"dispatch": "possible stroke"})
    c.post("/api/transcript", json={"text": "sats 400, heart rate 92", "use_llm": False})
    e = c.get("/api/state").json()["transcripts"][-1]
    assert [f["key"] for f in e["trace"]["rules"]["facts"]] == ["vitals.hr"]
    assert e["trace"]["rules"]["rejected"][0]["key"] == "vitals.spo2"
    assert "implausible" in e["trace"]["rules"]["rejected"][0]["reason"]
