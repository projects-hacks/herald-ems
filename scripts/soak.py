#!/usr/bin/env python3
"""Exercise the live Herald demo loop and measure stability over time.

The default run is the C3.8 acceptance soak: 30 minutes, one stroke scenario
after another, with the relay authorized through Toxiproxy.  Results are JSONL
so a failed or interrupted run still leaves useful evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

from herald.config import get_settings


GIB = 1024 ** 3


def lkw_time(minutes_ago: int, timezone_name: str, now: datetime | None = None) -> str:
    """Return a scenario clock time in the same zone the Herald server uses."""
    zone = ZoneInfo(timezone_name)
    current = now.astimezone(zone) if now is not None else datetime.now(zone)
    return (current - timedelta(minutes=minutes_ago)).strftime("%-I:%M")


def confirmable_facts(state: dict[str, Any], key_prefix: str) -> list[dict[str, Any]]:
    """Latest facts plus every dose/procedure event matching a confirmation step."""
    facts = list((state.get("facts") or {}).values())
    events = [event for rows in (state.get("events") or {}).values() for event in rows]
    return list({fact["id"]: fact for fact in [*facts, *events]
                 if fact["key"].startswith(key_prefix) and fact["status"] == "unconfirmed"}.values())


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    rows = sorted(values)
    pos = (len(rows) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return rows[lo]
    return rows[lo] + (rows[hi] - rows[lo]) * (pos - lo)


def memory_snapshot(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    fields: dict[str, int] = {}
    for line in path.read_text().splitlines():
        name, raw = line.split(":", 1)
        fields[name] = int(raw.strip().split()[0]) * 1024
    total, available = fields["MemTotal"], fields["MemAvailable"]
    return {"total_bytes": total, "available_bytes": available, "used_bytes": total - available}


def parse_competing_jobs(text: str) -> list[dict[str, Any]]:
    jobs = []
    scripts = ("vision_bench.py", "bench_extract.py", "train_lora.py", "merge_lora.py")
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, command, args = parts
        try:
            argv = shlex.split(args)
        except ValueError:
            argv = args.split()
        program = Path(argv[0]).name if argv else command
        target = Path(argv[1]).name if len(argv) > 1 else ""
        is_python_job = program.startswith("python") and target in scripts
        is_download = ((program == "hf" and len(argv) > 1 and argv[1] == "download") or
                       (program.startswith("python") and target == "hf" and len(argv) > 2 and
                        argv[2] == "download"))
        if is_python_job or is_download:
            jobs.append({"pid": int(pid), "command": command, "args": args[-500:]})
    return jobs


def competing_jobs() -> list[dict[str, Any]]:
    """GPU/large-I/O work that invalidates an isolated soak comparison on this shared machine."""
    result = subprocess.run(["ps", "-eo", "pid=,comm=,args="], text=True, capture_output=True, timeout=5)
    return parse_competing_jobs(result.stdout)


def parse_zrt_status(text: str) -> dict[str, Any]:
    unified = None
    match = re.search(r"Unified Memory.*?([0-9.]+)\s*/\s*([0-9.]+)\s*GB", text)
    if match:
        unified = {"used_gb": float(match.group(1)), "total_gb": float(match.group(2))}
    services = []
    for line in text.splitlines():
        if "│" not in line or "http://127.0.0.1:8080" not in line:
            continue
        cells = [cell.strip() for cell in line.strip("│").split("│")]
        if len(cells) >= 7:
            services.append({"pid": int(cells[0]), "uri": cells[1], "label": cells[2],
                             "status": cells[4], "memory": cells[5], "uptime": cells[6]})
    return {"unified_memory": unified, "services": services}


def zrt_snapshot() -> dict[str, Any]:
    result = subprocess.run(["sg", "zrt", "-c", "zrt status"], text=True, capture_output=True, timeout=15)
    raw = (result.stdout + result.stderr).strip()
    parsed = parse_zrt_status(raw)
    parsed.update(ok=result.returncode == 0, error=None if result.returncode == 0 else raw[-500:])
    return parsed


def model_backend(label: str, log_dir: Path = Path("/opt/hp/zrt/run")) -> str | None:
    """Return the last kernel-backend announcement for a served model, when vLLM prints one."""
    path = log_dir / f"vllm-{label}.log"
    if not path.exists():
        return None
    for line in reversed(path.read_text(errors="replace").splitlines()):
        if re.search(r"\busing\b.*\bbackend\b", line, re.IGNORECASE):
            return line.strip()
    return None


def summarize(events: list[dict[str, Any]], duration_s: float, target_duration_s: float) -> dict[str, Any]:
    model_rows = [e for e in events if e.get("type") == "model"]
    samples = [e for e in events if e.get("type") == "sample"]
    latencies = [float(e["latency_ms"]) for e in model_rows if e.get("latency_ms") is not None]
    first = [float(e["latency_ms"]) for e in model_rows
             if e.get("latency_ms") is not None and e["elapsed_s"] <= 300]
    last_start = max(0.0, duration_s - 300)
    last = [float(e["latency_ms"]) for e in model_rows
            if e.get("latency_ms") is not None and e["elapsed_s"] >= last_start]
    first_p95, last_p95 = percentile(first, .95), percentile(last, .95)
    drift_pct = None if not first_p95 or last_p95 is None else 100 * (last_p95 - first_p95) / first_p95
    used = [e["memory"]["used_bytes"] for e in samples]
    final_growth = used[-1] - used[0] if len(used) >= 2 else None
    peak_growth = max(used) - used[0] if len(used) >= 2 else None
    model_errors = sum(e.get("status") != "done" for e in model_rows)
    iteration_errors = sum(bool(e.get("error")) for e in events if e.get("type") == "iteration")
    relay_failures = sum(int(e.get("relay_failures", 0)) for e in events if e.get("type") == "iteration")
    contention = {(job["pid"], job["args"]) for e in samples for job in e.get("competing_jobs", [])}
    scenario_steps = [e for e in events if e.get("type") == "scenario_step"]
    checks = {
        "duration_reached": duration_s >= target_duration_s,
        "model_errors_zero": model_errors == 0,
        "iteration_errors_zero": iteration_errors == 0,
        "relay_failures_zero": relay_failures == 0,
        "no_competing_jobs": not contention,
        "latency_drift_within_20_pct": drift_pct is not None and drift_pct <= 20,
        "final_memory_growth_within_1_gib": final_growth is not None and final_growth <= GIB,
    }
    return {
        "duration_s": round(duration_s, 1), "target_duration_s": target_duration_s,
        "iterations": sum(e.get("type") == "iteration" for e in events),
        "model_calls": len(model_rows), "model_errors": model_errors, "iteration_errors": iteration_errors,
        "relay_failures": relay_failures,
        "latency_ms": {"p95_all": percentile(latencies, .95), "p95_first_5m": first_p95,
                       "p95_last_5m": last_p95, "drift_pct": drift_pct},
        "memory": {"final_growth_bytes": final_growth, "peak_growth_bytes": peak_growth},
        "competing_jobs": [{"pid": pid, "args": args} for pid, args in sorted(contention)],
        "scenario_steps": {
            "done": sum(e.get("status") == "done" for e in scenario_steps),
            "skipped": sum(e.get("status") == "skipped" for e in scenario_steps),
        },
        "checks": checks, "passed": all(checks.values()),
    }


class Recorder:
    def __init__(self, path: Path, started: float):
        self.path, self.started, self.events = path, started, []
        path.parent.mkdir(parents=True, exist_ok=True)
        self.out = path.open("w")

    def write(self, event: dict[str, Any]) -> None:
        row = {"at": datetime.now(timezone.utc).isoformat(),
               "elapsed_s": round(time.monotonic() - self.started, 3), **event}
        self.events.append(row)
        self.out.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
        self.out.flush()

    def close(self) -> None:
        self.out.close()


def wait_model(client: httpx.Client, entry_id: str, timeout_s: float,
               on_wait: Callable[[], None]) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        on_wait()
        entries = client.get("/api/state").raise_for_status().json()["transcripts"]
        entry = next((row for row in entries if row["id"] == entry_id), None)
        if entry and entry["trace"]["model"]["status"] != "running":
            return entry
        time.sleep(.1)
    raise TimeoutError(f"model phase for {entry_id} exceeded {timeout_s:.0f}s")


def run_scenario(client: httpx.Client, scenario: dict[str, Any], recorder: Recorder,
                 model_timeout_s: float, sample_due: Callable[[], None], lkw_minutes_ago: int,
                 timezone_name: str) -> dict[str, Any]:
    dispatch = next((s["incident"] for s in scenario["steps"] if "incident" in s), "possible stroke")
    client.post("/api/incident", json={"dispatch": dispatch}).raise_for_status()
    client.post("/api/relay/authorize", json={"destination": "Regional",
                                               "scope": "stroke pre-alert set"}).raise_for_status()
    lkw = lkw_time(lkw_minutes_ago, timezone_name)
    for step_index, step in enumerate(scenario["steps"]):
        sample_due()
        if "incident" in step:
            continue
        if "say" in step:
            spoken = step["say"].replace("LKW_TIME", lkw)
            response = client.post("/api/transcript", json={"text": spoken,
                "captured_by": step.get("by", "medic"), "speaker": step.get("speaker"), "use_llm": True})
            response.raise_for_status()
            entry_id = response.json()["transcript"]["id"]
            try:
                entry = wait_model(client, entry_id, model_timeout_s, sample_due)
                model = entry["trace"]["model"]
                recorder.write({"type": "model", "entry_id": entry_id, "step": step_index, "text": spoken,
                                "status": model["status"],
                                "latency_ms": model.get("ms"), "facts": len(model.get("facts", [])),
                                "error": model.get("error")})
            except Exception as exc:
                recorder.write({"type": "model", "entry_id": entry_id, "step": step_index, "text": spoken,
                                "status": "timeout",
                                "latency_ms": None, "facts": 0, "error": str(exc)})
        elif "confirm" in step:
            state = client.get("/api/state").raise_for_status().json()
            facts = confirmable_facts(state, step["confirm"])
            for fact in facts:
                client.post(f"/api/facts/{fact['id']}/confirm").raise_for_status()
            recorder.write({"type": "scenario_step", "kind": "confirm", "step": step_index,
                            "status": "done", "facts": len(facts)})
        elif "photo" in step:
            with Path(step["photo"]).open("rb") as image:
                response = client.post("/api/photo", files={"file": ("photo.jpg", image, "image/jpeg")},
                                       data={"mode": step.get("mode", "monitor")})
            if response.status_code in (404, 503):
                recorder.write({"type": "scenario_step", "kind": "photo", "step": step_index,
                                "status": "skipped", "reason": f"HTTP {response.status_code}"})
            else:
                response.raise_for_status()
                recorder.write({"type": "scenario_step", "kind": "photo", "step": step_index,
                                "status": "done", "facts": len(response.json().get("facts", []))})
        elif "ask" in step:
            response = client.get("/api/protocols/search", params={"q": step["ask"]})
            deadline = time.monotonic() + model_timeout_s
            while (response.status_code == 503 and isinstance(response.json().get("detail"), dict)
                   and response.json()["detail"].get("building") and time.monotonic() < deadline):
                time.sleep(min(5, max(0, deadline - time.monotonic())))
                response = client.get("/api/protocols/search", params={"q": step["ask"]})
            if response.status_code in (404, 503):
                recorder.write({"type": "scenario_step", "kind": "ask", "step": step_index,
                                "status": "skipped", "reason": f"HTTP {response.status_code}"})
            else:
                response.raise_for_status()
                recorder.write({"type": "scenario_step", "kind": "ask", "step": step_index,
                                "status": "done", "answerable": bool(response.json().get("answerable"))})
        elif "handoff" in step:
            response = client.get("/api/handoff")
            if response.status_code in (404, 503):
                recorder.write({"type": "scenario_step", "kind": "handoff", "step": step_index,
                                "status": "skipped", "reason": f"HTTP {response.status_code}"})
            else:
                response.raise_for_status()
                recorder.write({"type": "scenario_step", "kind": "handoff", "step": step_index,
                                "status": "done", "has_text": bool(response.json().get("text"))})
        elif "monitor" in step:
            facts = [{"key": k, "value": v, "captured_by": "device", "role": "device",
                      "speaker": "monitor", "confidence": .99} for k, v in step["monitor"].items()]
            client.post("/api/facts", json=facts).raise_for_status()
        else:
            raise ValueError(f"unsupported scenario step {step_index}: {sorted(step)}")
    time.sleep(.5)
    state = client.get("/api/state").raise_for_status().json()
    failures = sum(row.get("result") == "failed" for row in state["relay"]["log"])
    return {"relay_failures": failures, "relay_link": state["relay"]["link"],
            "packets_acked": state["relay"]["packets_acked"], "summary": state["summary"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8103")
    parser.add_argument("--scenario", default="scenarios/stroke_demo.json")
    parser.add_argument("--duration-minutes", type=float, default=30)
    parser.add_argument("--sample-interval", type=float, default=30)
    parser.add_argument("--model-timeout", type=float, default=30)
    parser.add_argument("--lkw-minutes-ago", type=int, default=64)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-pass", action="store_true", help="exit nonzero unless all C3.8 checks pass")
    parser.add_argument("--allow-contention", action="store_true",
                        help="continue after a competing benchmark/download is observed (the run cannot pass)")
    args = parser.parse_args()
    settings = get_settings()
    started = time.monotonic()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or Path("runs") / f"soak_{stamp}.jsonl"
    recorder = Recorder(output, started)
    duration_s = args.duration_minutes * 60
    deadline, next_sample = started + duration_s, started

    def sample_due(force: bool = False) -> None:
        nonlocal next_sample
        if not force and time.monotonic() < next_sample:
            return
        recorder.write({"type": "sample", "memory": memory_snapshot(), "zrt": zrt_snapshot(),
                        "loadavg": list(Path("/proc/loadavg").read_text().split()[:3]),
                        "competing_jobs": competing_jobs()})
        next_sample = time.monotonic() + args.sample_interval

    try:
        scenario = json.loads(Path(args.scenario).read_text())
        with httpx.Client(base_url=args.url, timeout=max(10, args.model_timeout + 5)) as client:
            health = client.get("/api/health").raise_for_status().json()
            client.post("/api/netem/good").raise_for_status()
            recorder.write({"type": "meta", "url": args.url, "scenario": scenario.get("name"),
                            "health": health, "target_duration_s": duration_s,
                            "model_backends": {label: model_backend(label) for label in
                                               (health.get("llm_model"), health.get("vision_model")) if label}})
            sample_due(True)
            iteration = 0
            while time.monotonic() < deadline:
                if not args.allow_contention and any(e.get("competing_jobs") for e in recorder.events
                                                     if e.get("type") == "sample"):
                    recorder.write({"type": "abort", "reason": "competing job detected"})
                    break
                iteration += 1
                try:
                    result = run_scenario(client, scenario, recorder, args.model_timeout, sample_due,
                                          args.lkw_minutes_ago, settings.timezone)
                    recorder.write({"type": "iteration", "iteration": iteration, **result})
                except Exception as exc:
                    recorder.write({"type": "iteration", "iteration": iteration, "relay_failures": 0,
                                    "error": str(exc)})
                sample_due()
            sample_due(True)
    finally:
        elapsed = time.monotonic() - started
        summary = summarize(recorder.events, elapsed, duration_s)
        recorder.write({"type": "summary", **summary})
        recorder.close()
        summary_path = output.with_suffix(".summary.json")
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({"output": str(output), "summary": str(summary_path), **summary}, indent=2))
    return 0 if not args.require_pass or summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
