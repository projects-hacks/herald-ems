#!/usr/bin/env python3
"""Measure Herald's real relay path over a reproducible Toxiproxy weak link.

The benchmark uses a deterministic stroke record and the real HTTP Relay -> Toxiproxy ->
ED receiver path. It does not start Herald, load a model, or perform any inference.

Start an ED receiver and Toxiproxy on unused local ports, then run three times:

  $PY -m uvicorn ed_receiver.app:app --host 127.0.0.1 --port 8210
  ~/.local/bin/toxiproxy-server -host 127.0.0.1 -port 8475
  $PY eval/bench_relay.py --toxiproxy-url http://127.0.0.1:8475 \
      --ed-url http://127.0.0.1:8210 --listen 127.0.0.1:9101 --runs 3

Each run applies 1 KB/s bandwidth in both directions and 800 ms downstream latency.
It records: time to the first critical acknowledgement, bytes in that critical packet
versus the real full-record sync, time to reconciliation, and ED duplicates/losses.
Summary rows append to eval/results.jsonl unless --out is changed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baselines.rules_extractor import extract  # noqa: E402 -- deterministic benchmark input only
from herald.core.incident import Incident  # noqa: E402
from herald.core.schema import Status  # noqa: E402
from herald.relay import Relay  # noqa: E402

WEAK_TOXICS = (
    {"name": "bandwidth_up", "type": "bandwidth", "stream": "upstream", "attributes": {"rate": 1}},
    {"name": "bandwidth_down", "type": "bandwidth", "stream": "downstream", "attributes": {"rate": 1}},
    {"name": "latency_down", "type": "latency", "stream": "downstream", "attributes": {"latency": 800, "jitter": 0}},
)
METRICS = ("first_critical_ack_ms", "critical_packet_bytes", "full_sync_bytes", "time_to_reconcile_ms",
           "duplicates", "losses")


def build_incident() -> Incident:
    """A fixed, confirmed stroke record; this evaluates relay transport only, not extraction."""
    inc = Incident(dispatch="possible stroke")
    lines = (
        "68-year-old female, sudden left-sided weakness, husband says she was fine at 1:40.",
        "Mild left facial droop, left arm and leg can't lift, eyes deviated to the right, no agnosia.",
        "Onset was witnessed. BP 182 over 104, pulse 92, SpO2 95 on room air, respirations 18, temp 37.1, alert.",
        "She takes warfarin. Glucose 142. Transporting to Valley Medical, ETA 12 minutes.",
    )
    for line in lines:
        for fact_in in extract(line):
            fact = inc.ingest(fact_in, record=False)
            if fact.status is not Status.confirmed:
                inc.set_status(fact.id, Status.confirmed, actor="benchmark")
    inc.commit()
    return inc


class Toxiproxy:
    def __init__(self, api_url: str, name: str, listen: str, upstream: str):
        self.client = httpx.Client(base_url=api_url.rstrip("/"), timeout=5.0)
        self.name, self.listen, self.upstream = name, listen, upstream
        self.created = False

    def ensure(self, reuse: bool = False) -> None:
        response = self.client.get(f"/proxies/{self.name}")
        if response.status_code == 404:
            created = self.client.post("/proxies", json={"name": self.name, "listen": self.listen,
                                                           "upstream": self.upstream, "enabled": True})
            created.raise_for_status()
            self.created = True
            return
        response.raise_for_status()
        existing = response.json()
        if existing["listen"] != self.listen or existing["upstream"] != self.upstream:
            raise RuntimeError(f"proxy '{self.name}' already points to {existing['listen']} -> {existing['upstream']}; "
                               "choose a different --proxy-name")
        if not reuse:
            raise RuntimeError(f"proxy '{self.name}' already exists; choose a different --proxy-name or pass "
                               "--reuse-proxy only if it is this benchmark's dedicated proxy")

    def _clear_toxics(self) -> None:
        proxy = self.client.get(f"/proxies/{self.name}").raise_for_status().json()
        for toxic in proxy.get("toxics", []):
            self.client.delete(f"/proxies/{self.name}/toxics/{toxic['name']}").raise_for_status()

    def weak(self) -> None:
        self._clear_toxics()
        self.client.post(f"/proxies/{self.name}", json={"enabled": True}).raise_for_status()
        for toxic in WEAK_TOXICS:
            self.client.post(f"/proxies/{self.name}/toxics", json=toxic).raise_for_status()

    def good(self) -> None:
        self._clear_toxics()
        self.client.post(f"/proxies/{self.name}", json={"enabled": True}).raise_for_status()

    def delete_if_created(self) -> None:
        if self.created:
            response = self.client.delete(f"/proxies/{self.name}")
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()
        self.client.close()


def receiver_state(ed_url: str) -> dict:
    with httpx.Client(base_url=ed_url.rstrip("/"), timeout=5.0) as client:
        client.post("/reset").raise_for_status()
        return client.get("/state").raise_for_status().json()


def losses(expected: dict[str, Any], state: dict, incident_id: str) -> int:
    fields = state.get("incidents", {}).get(incident_id, {}).get("fields", {})
    return sum(1 for key, value in expected.items() if fields.get(key, {}).get("v") != value)


async def drain_after_good_link(relay: Relay, incident: Incident, timeout_s: float) -> tuple[dict, int]:
    """Return the acknowledged full-sync log entry and wall time after the link becomes good."""
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        entry = await relay.tick()
        if entry and entry["result"] == "acked" and entry["tier"] == "full":
            full = entry
        else:
            full = None
        if full and not relay.pending() and relay.inflight is None:
            return full, round((time.perf_counter() - started) * 1000)
    raise TimeoutError(f"relay did not reconcile within {timeout_s:g} seconds")


async def run_once_with_proxy(ed_url: str, proxy_url: str, toxiproxy: Toxiproxy, timeout_s: float) -> dict:
    receiver_state(ed_url)
    toxiproxy.weak()
    inc = build_incident()
    relay = Relay(lambda: inc, ed_url=proxy_url)
    relay.authorize("Valley Medical")
    started = time.perf_counter()
    first = await relay.tick()
    if not first or first["result"] != "acked" or first["tier"] != "critical":
        raise RuntimeError(f"expected first weak-link critical acknowledgement, got {first}")
    first_critical_ack_ms = round((time.perf_counter() - started) * 1000)

    toxiproxy.good()
    relay.results.clear()                 # actual proxy is now good; discard the deliberately weak RTT sample
    relay.results.extend(((True, 1.0), (True, 1.0), (True, 1.0)))
    full, post_recovery_ms = await drain_after_good_link(relay, inc, timeout_s)
    with httpx.Client(base_url=ed_url.rstrip("/"), timeout=5.0) as client:
        state = client.get("/state").raise_for_status().json()
    ed_incident = state["incidents"].get(inc.id, {})
    return {
        "first_critical_ack_ms": first_critical_ack_ms,
        "critical_packet_bytes": first["bytes"],
        "full_sync_bytes": full["bytes"],
        "critical_vs_full_pct": round(100 * first["bytes"] / full["bytes"], 2),
        "time_to_reconcile_ms": round(first_critical_ack_ms + post_recovery_ms),
        "duplicates": ed_incident.get("duplicates", 0),
        "losses": losses(relay.critical_values(), state, inc.id),
        "packets_acked": relay.packets_acked,
    }


def spread(rows: list[dict]) -> dict:
    out = {}
    for metric in METRICS:
        values = [row[metric] for row in rows]
        out[metric] = {"mean": round(statistics.mean(values), 2), "min": min(values), "max": max(values),
                       "runs": len(values)}
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ed-url", default="http://127.0.0.1:8210")
    p.add_argument("--toxiproxy-url", default="http://127.0.0.1:8475")
    p.add_argument("--listen", default="127.0.0.1:9101", help="dedicated Toxiproxy listener")
    p.add_argument("--proxy-name", default="herald_relay_bench")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--timeout", type=float, default=30.0, help="seconds allowed after recovery")
    p.add_argument("--out", default="eval/results.jsonl", help="append one JSON result per run here")
    p.add_argument("--keep-proxy", action="store_true", help="leave a proxy created by this benchmark in place")
    p.add_argument("--reuse-proxy", action="store_true", help="reuse the named dedicated benchmark proxy")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    upstream = args.ed_url.removeprefix("http://").removeprefix("https://")
    proxy_url = f"http://{args.listen}"
    toxiproxy = Toxiproxy(args.toxiproxy_url, args.proxy_name, args.listen, upstream)
    rows = []
    configured = False
    try:
        toxiproxy.ensure(reuse=args.reuse_proxy)
        configured = True
        for run in range(1, args.runs + 1):
            metrics = asyncio.run(run_once_with_proxy(args.ed_url, proxy_url, toxiproxy, args.timeout))
            row = {"bench": "relay", "run": run, "link": {"bandwidth_kb_s": 1, "latency_ms": 800},
                   **metrics, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            rows.append(row)
            output_path = Path(args.out)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("a") as output:
                output.write(json.dumps(row, default=str) + "\n")
            print(json.dumps(row, default=str))
        print(json.dumps({"bench": "relay", "runs": args.runs, "spread": spread(rows)}, indent=1))
    finally:
        if configured:
            toxiproxy.good()
        if not args.keep_proxy:
            toxiproxy.delete_if_created()


if __name__ == "__main__":
    main()
