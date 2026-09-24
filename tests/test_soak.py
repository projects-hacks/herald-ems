import importlib.util
from datetime import datetime, timezone
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("soak", Path(__file__).parents[1] / "scripts" / "soak.py")
soak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(soak)


def test_percentile_interpolates_and_handles_empty():
    assert soak.percentile([], .95) is None
    assert soak.percentile([10], .95) == 10
    assert soak.percentile([10, 20, 30, 40], .5) == 25


def test_lkw_time_uses_server_timezone():
    instant = datetime(2026, 9, 25, 1, 30, tzinfo=timezone.utc)
    assert soak.lkw_time(60, "America/Los_Angeles", instant) == "5:30"


def test_confirmable_facts_includes_every_matching_record_event():
    state = {
        "facts": {"procedures.done": {"id": "latest-procedure", "key": "procedures.done",
                                         "status": "unconfirmed"}},
        "events": {
            "meds.given": [
                {"id": "dose-1", "key": "meds.given", "status": "unconfirmed"},
                {"id": "dose-2", "key": "meds.given", "status": "confirmed"},
            ],
            "procedures.done": [
                {"id": "procedure-1", "key": "procedures.done", "status": "unconfirmed"},
                {"id": "latest-procedure", "key": "procedures.done", "status": "unconfirmed"},
            ],
        },
    }
    assert {f["id"] for f in soak.confirmable_facts(state, "meds.")} == {"dose-1"}
    assert {f["id"] for f in soak.confirmable_facts(state, "procedures.")} == {
        "procedure-1", "latest-procedure"
    }


def test_scenario_records_optional_steps_and_confirms_record_events(tmp_path, monkeypatch):
    class Response:
        def __init__(self, data=None, status=200):
            self.data, self.status_code = data or {}, status

        def json(self):
            return self.data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")
            return self

    state = {
        "facts": {},
        "events": {"meds.given": [
            {"id": "dose-1", "key": "meds.given", "status": "unconfirmed"},
        ]},
        "relay": {"log": [], "link": "good", "packets_acked": 0},
        "summary": "test",
    }

    class Client:
        def __init__(self):
            self.posts = []

        def post(self, path, **kwargs):
            self.posts.append(path)
            return Response(status=503) if path == "/api/photo" else Response()

        def get(self, path, **kwargs):
            if path == "/api/protocols/search":
                return Response(status=404)
            if path == "/api/handoff":
                return Response({"text": "handoff"})
            return Response(state)

    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"test")
    scenario = {"steps": [
        {"incident": "test"},
        {"confirm": "meds."},
        {"photo": str(photo)},
        {"ask": "protocol"},
        {"handoff": True},
    ]}
    recorder = soak.Recorder(tmp_path / "events.jsonl", 0)
    monkeypatch.setattr(soak.time, "monotonic", lambda: 0)
    monkeypatch.setattr(soak.time, "sleep", lambda _: None)
    client = Client()
    soak.run_scenario(client, scenario, recorder, 1, lambda: None, 60, "America/Los_Angeles")
    recorder.close()

    steps = {(event["kind"], event["status"]) for event in recorder.events
             if event.get("type") == "scenario_step"}
    assert steps == {("confirm", "done"), ("photo", "skipped"),
                     ("ask", "skipped"), ("handoff", "done")}
    assert "/api/facts/dose-1/confirm" in client.posts


def test_parse_zrt_status_reads_resources_and_services():
    text = """
  Unified Memory   [bar] 98.9 / 121.6 GB
│ 369345 │ hf:team/extractor │ ems-e-v2-fp8 │ http://127.0.0.1:8080 │ Ready │ 14.5 GB (VRAM) │ 8h ago │
"""
    status = soak.parse_zrt_status(text)
    assert status["unified_memory"] == {"used_gb": 98.9, "total_gb": 121.6}
    assert status["services"][0]["label"] == "ems-e-v2-fp8"
    assert status["services"][0]["status"] == "Ready"


def test_model_backend_ignores_backends_module_path(tmp_path):
    (tmp_path / "vllm-model.log").write_text(
        "Using DEEPGEMM Fp8 MoE backend out of potential backends\n"
        "Using cache directory: /tmp/vllm/backends.py/cache\n")
    assert "DEEPGEMM" in soak.model_backend("model", tmp_path)


def test_competing_jobs_ignores_parent_shell_and_python_postprocessing():
    text = """
12 bash /bin/bash -c nohup python eval/vision_bench.py &
13 python /env/bin/python eval/vision_bench.py --runs 3
14 python /env/bin/python -c print('eval/vision_bench.py')
15 python3.12 /env/bin/hf download Qwen/model
16 hf /env/bin/hf download Qwen/model
"""
    jobs = soak.parse_competing_jobs(text)
    assert [job["pid"] for job in jobs] == [13, 15, 16]


def test_summary_applies_acceptance_checks():
    events = [
        {"type": "sample", "elapsed_s": 0, "memory": {"used_bytes": 10 * soak.GIB}},
        {"type": "model", "elapsed_s": 10, "status": "done", "latency_ms": 1000},
        {"type": "iteration", "elapsed_s": 100, "relay_failures": 0},
        {"type": "model", "elapsed_s": 1700, "status": "done", "latency_ms": 1100},
        {"type": "sample", "elapsed_s": 1800, "memory": {"used_bytes": 10.5 * soak.GIB}},
    ]
    summary = soak.summarize(events, 1800, 1800)
    assert summary["passed"] is True
    assert summary["latency_ms"]["drift_pct"] == 10
    assert summary["scenario_steps"] == {"done": 0, "skipped": 0}


def test_summary_fails_on_errors_retries_drift_and_growth():
    events = [
        {"type": "sample", "elapsed_s": 0, "memory": {"used_bytes": 10 * soak.GIB}},
        {"type": "model", "elapsed_s": 10, "status": "done", "latency_ms": 1000},
        {"type": "iteration", "elapsed_s": 100, "relay_failures": 1},
        {"type": "model", "elapsed_s": 1700, "status": "error", "latency_ms": 1400},
        {"type": "sample", "elapsed_s": 1800, "memory": {"used_bytes": 12 * soak.GIB}},
    ]
    summary = soak.summarize(events, 1800, 1800)
    assert summary["passed"] is False
    assert summary["model_errors"] == 1
    assert summary["iteration_errors"] == 0
    assert summary["relay_failures"] == 1
    assert summary["checks"]["latency_drift_within_20_pct"] is False
    assert summary["checks"]["final_memory_growth_within_1_gib"] is False


def test_summary_rejects_a_contended_run():
    events = [
        {"type": "sample", "elapsed_s": 0, "memory": {"used_bytes": 10 * soak.GIB},
         "competing_jobs": [{"pid": 42, "args": "python eval/vision_bench.py"}]},
        {"type": "model", "elapsed_s": 10, "status": "done", "latency_ms": 1000},
        {"type": "model", "elapsed_s": 1700, "status": "done", "latency_ms": 1000},
        {"type": "sample", "elapsed_s": 1800, "memory": {"used_bytes": 10 * soak.GIB},
         "competing_jobs": []},
    ]
    summary = soak.summarize(events, 1800, 1800)
    assert summary["checks"]["no_competing_jobs"] is False
    assert summary["competing_jobs"][0]["pid"] == 42
