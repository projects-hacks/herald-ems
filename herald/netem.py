"""Stage control for an emulated weak link, through Toxiproxy's HTTP API (userspace, no root).

The relay sends to the proxy's listen port; the proxy forwards to the real ED receiver.
Modes: good (no toxics), weak (~8 kbit/s, high latency, 30% of connections reset), down (proxy disabled).
Say on stage: "emulated weak link, real packets".
"""
from __future__ import annotations

import os

import httpx

API = os.getenv("TOXIPROXY_URL", "http://127.0.0.1:8474")
NAME = "ed_link"


def ensure(listen: str, upstream: str) -> dict:
    with httpx.Client(base_url=API, timeout=3) as c:
        r = c.get(f"/proxies/{NAME}")
        if r.status_code == 404:
            r = c.post("/proxies", json={"name": NAME, "listen": listen, "upstream": upstream, "enabled": True})
        r.raise_for_status()
        return r.json()


def set_mode(mode: str) -> dict:
    with httpx.Client(base_url=API, timeout=3) as c:
        proxy = c.get(f"/proxies/{NAME}").raise_for_status().json()
        for t in proxy.get("toxics", []):
            c.delete(f"/proxies/{NAME}/toxics/{t['name']}")
        c.post(f"/proxies/{NAME}", json={"enabled": mode != "down"}).raise_for_status()
        if mode == "weak":
            for body in [
                {"name": "bw_up", "type": "bandwidth", "stream": "upstream", "attributes": {"rate": 1}},
                {"name": "bw_down", "type": "bandwidth", "stream": "downstream", "attributes": {"rate": 1}},
                {"name": "lat", "type": "latency", "stream": "downstream", "attributes": {"latency": 800, "jitter": 400}},
                {"name": "flaky", "type": "reset_peer", "stream": "upstream", "toxicity": 0.3, "attributes": {"timeout": 0}},
            ]:
                c.post(f"/proxies/{NAME}/toxics", json=body).raise_for_status()
        return c.get(f"/proxies/{NAME}").json()
