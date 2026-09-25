"""Egress policy (E1): the one place every outbound HTTP call decides ALLOW / QUEUE / DENY before it happens.

Three kinds of destination exist, and the policy tells them apart by host alone:
  - a local model endpoint (127.0.0.1 / localhost / ::1) -- always ALLOW, never counted as a cloud escalation:
    inference never leaves this box (AGENTS.md invariant 1).
  - an allow-listed ED host (config/egress.yaml `ed_allow_list`, plus whatever HERALD_ED_URL / HERALD_PROTOCOL_MIRROR
    the deployment configured -- an operator's own choice, added automatically) -- ALLOW when the link isn't known
    to be down, QUEUE when it is (retried once the link recovers; nothing is lost or silently dropped).
  - anything else -- DENY by default, and counted as a refused cloud call. Herald never sends patient data, or asks
    a model, off this box without an explicit allow-list entry.

Every decision is appended to a bounded log (`decision_log_size`, config/egress.yaml) so GET /api/egress can show
exactly what was allowed, queued or refused, and why -- not just a running total.
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import urlsplit

from ..config import load_yaml

_LOCAL = re.compile(r"^(127\.0\.0\.1|localhost|::1)$", re.IGNORECASE)


def host_of(url: str) -> str:
    """The bare host (no scheme, no port) a URL or a plain "host" / "host:port" string names."""
    if not url:
        return ""
    candidate = url if "//" in url else f"//{url}"
    parsed = urlsplit(candidate)
    host = parsed.hostname
    if host:
        return host.lower()
    return url.split(":")[0].strip().lower()


@dataclass(frozen=True)
class Decision:
    action: str            # "allow" | "queue" | "deny"
    reason: str
    counted_cloud: bool    # True only for a refused (denied) call: the one number `cloud_ai_calls` must stay true to
    url: str
    host: str
    purpose: str
    at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason, "counted_cloud": self.counted_cloud,
                "url": self.url, "host": self.host, "purpose": self.purpose, "at": self.at}


class EgressPolicy:
    """Config-driven (config/egress.yaml) decision point, with counters and a bounded decision log."""

    def __init__(self, ed_allow_list: Iterable[str] = (), decision_log_size: int = 200):
        self.allow_hosts = {host_of(h) for h in ed_allow_list if host_of(h)}
        self.log: deque = deque(maxlen=decision_log_size)
        self.counts = {"allow_local": 0, "allow_ed": 0, "queue": 0, "deny": 0}

    def decide(self, url: Optional[str], *, purpose: str = "", link_state: str = "unknown") -> Decision:
        host = host_of(url or "")
        if _LOCAL.match(host):
            d = Decision("allow", "local model endpoint on this box; inference never leaves it (AGENTS.md "
                         "invariant 1); not counted as a cloud escalation", False, url or "", host, purpose)
            self.counts["allow_local"] += 1
        elif host and host in self.allow_hosts:
            if link_state == "down":
                d = Decision("queue", f"{host} is an allow-listed destination (config/egress.yaml) but the link "
                             "is reporting down; queued for the next good/weak reading", False, url or "", host, purpose)
                self.counts["queue"] += 1
            else:
                d = Decision("allow", f"{host} is on config/egress.yaml's allow-list", False, url or "", host, purpose)
                self.counts["allow_ed"] += 1
        else:
            d = Decision("deny", f"{host or url!r} is not a local model endpoint or an allow-listed destination; "
                         "refused by default (config/egress.yaml ed_allow_list)", True, url or "", host, purpose)
            self.counts["deny"] += 1
        self.log.append(d.as_dict())
        return d

    def snapshot(self) -> dict:
        """counts + a bounded recent log, for GET /api/egress and the telemetry/system/snapshot counters."""
        return {
            "allow_hosts": sorted(self.allow_hosts),
            "counts": dict(self.counts),
            "cloud_ai_calls": 0,                       # calls actually made to a non-local, non-allow-listed
                                                        # endpoint: always 0 -- DENY happens before the request.
            "cloud_calls_refused": self.counts["deny"],  # what would have been a cloud escalation, and was stopped
            "queued": self.counts["queue"],
            "log": list(self.log)[-50:],
        }


def default_policy(settings=None) -> EgressPolicy:
    """The policy built from config/egress.yaml plus this deployment's own configured hosts.

    HERALD_ED_URL and HERALD_PROTOCOL_MIRROR (herald/config/settings.py) are an operator's explicit choice of
    where this box may send data or fetch protocol updates from; naming them in the environment allow-lists them
    the same way listing them in config/egress.yaml would.
    """
    cfg = load_yaml("egress.yaml")
    allow = list(cfg.get("ed_allow_list") or [])
    if settings is not None:
        if getattr(settings, "ed_url", None):
            allow.append(settings.ed_url)
        if getattr(settings, "protocol_mirror", None):
            allow.append(settings.protocol_mirror)
    return EgressPolicy(allow, decision_log_size=int(cfg.get("decision_log_size", 200)))
