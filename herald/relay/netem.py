"""Stage control for an emulated weak link, through Toxiproxy's HTTP API (userspace, no root). Demo only.

The relay sends to the proxy's listen port; the proxy forwards to the real ED receiver.
Modes: good (no toxics), weak (~8 kbit/s, high latency, 30% of connections reset), down (proxy disabled).
Say on stage: "emulated weak link, real packets".
"""
from __future__ import annotations

import httpx

MODES = ("good", "weak", "down")
WEAK_TOXICS = [
    {"name": "bw_up", "type": "bandwidth", "stream": "upstream", "attributes": {"rate": 1}},
    {"name": "bw_down", "type": "bandwidth", "stream": "downstream", "attributes": {"rate": 1}},
    {"name": "lat", "type": "latency", "stream": "downstream", "attributes": {"latency": 800, "jitter": 400}},
    {"name": "flaky", "type": "reset_peer", "stream": "upstream", "toxicity": 0.3, "attributes": {"timeout": 0}},
]


class LinkEmulator:
    def __init__(self, api_url: str, proxy_name: str = "ed_link"):
        self.api, self.name = api_url, proxy_name

    def ensure(self, listen: str, upstream: str) -> dict:
        with httpx.Client(base_url=self.api, timeout=3) as c:
            r = c.get(f"/proxies/{self.name}")
            if r.status_code == 404:
                r = c.post("/proxies", json={"name": self.name, "listen": listen, "upstream": upstream, "enabled": True})
            r.raise_for_status()
            return r.json()

    def set_mode(self, mode: str) -> dict:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        with httpx.Client(base_url=self.api, timeout=3) as c:
            proxy = c.get(f"/proxies/{self.name}").raise_for_status().json()
            for t in proxy.get("toxics", []):
                c.delete(f"/proxies/{self.name}/toxics/{t['name']}")
            c.post(f"/proxies/{self.name}", json={"enabled": mode != "down"}).raise_for_status()
            if mode == "weak":
                for body in WEAK_TOXICS:
                    c.post(f"/proxies/{self.name}/toxics", json=body).raise_for_status()
            return c.get(f"/proxies/{self.name}").json()
