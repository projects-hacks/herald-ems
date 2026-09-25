"""Relay: keep the emergency department current over a bad link.

Three questions, all answered by plain code:
  1. What changed?                -> confirmed critical values that differ from what the ED acknowledged
  2. What doesn't the ED know?    -> the same set, in priority order (rules, with a rationale per tier)
  3. What can the link carry now? -> a byte budget from the measured link state (good / weak / down)

Only confirmed facts are ever sent. Every packet is sequenced and acknowledged; retries
reuse the same sequence number, so the receiver can apply them idempotently.
The medic authorizes the destination and scope once; in-scope updates then flow on their own.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from ..core.ports import Transport
from ..core.schema import utcnow
from ..scoring import ScaleRegistry, default_scales
from .tiers import RelayTiers, default_tiers


def _compact(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), default=str).encode()


class Relay:
    def __init__(self, incident_getter: Callable, ed_url: Optional[str] = None,
                 transport: Optional[Transport] = None, probe: Optional[Callable[[], Awaitable[None]]] = None,
                 tiers: Optional[RelayTiers] = None, scales: Optional[ScaleRegistry] = None,
                 audio_dir: Optional[Path] = None):
        self.get_incident = incident_getter
        self.ed_url = ed_url
        self.tiers = tiers or default_tiers()
        self.scales = scales or default_scales()
        self.audio_dir = audio_dir
        self._transport = transport
        self._probe = probe
        self.last_probe = 0.0
        self.reset()

    def reset(self) -> None:
        self.authorized: Optional[dict] = None
        self.acked: dict[str, Any] = {}          # key -> value the ED acknowledged
        self.seq = 0
        self.inflight: Optional[dict] = None     # packet being retried (same seq until acked)
        self.results: deque = deque(maxlen=8)    # (ok, rtt_ms)
        self.log: deque = deque(maxlen=40)
        self.bytes_sent = 0
        self.packets_acked = 0
        self.retries = 0
        self.full_synced_facts = 0
        self.last_ack_at: Optional[str] = None

    # ---------- configuration ----------
    @property
    def configured(self) -> bool:
        return bool(self.ed_url or self._transport)

    def authorize(self, destination: str, scope: str = "stroke pre-alert set") -> None:
        self.authorized = {"destination": destination, "scope": scope, "at": utcnow().isoformat()}

    # ---------- what the ED should know ----------
    def critical_values(self) -> dict[str, Any]:
        inc = self.get_incident()
        vals = inc.values(confirmed_only=True)
        out = {k: v for k, v in vals.items() if k in self.tiers}
        snap = inc.snapshot()                  # scores from confirmed facts, for the active county only
        for sid, r in snap["scores"].items():
            if sid in self.scales and f"score.{sid}" in self.tiers and (text := self.scales[sid].relay_text(r)):
                out[f"score.{sid}"] = text
        if snap["readiness"]:
            a = snap["readiness"][0]
            out["alert.readiness"] = f'{a["label"]} {a["done"]}/{a["total"]}{" ready" if a["ready"] else ""}'
        return out

    def pending(self) -> list[tuple[int, str, str, Any]]:
        cur = self.critical_values()
        rows = [(*self.tiers.priority[k], k, v) for k, v in cur.items() if self.acked.get(k) != v]
        return sorted(rows, key=lambda r: (r[0], r[2]))

    def withdrawals(self) -> list[tuple[int, str, str]]:
        """Confirmed values the ED acknowledged but the medic subsequently withdrew."""
        current = self.critical_values()
        rows = [(*self.tiers.priority[key], key) for key in self.acked if key not in current and key in self.tiers]
        return sorted(rows, key=lambda row: (row[0], row[2]))

    # ---------- link state ----------
    def link_state(self) -> str:
        if not self.results:
            return "unknown"
        recent = list(self.results)[-3:]
        if len(recent) >= 2 and not any(ok for ok, _ in recent[-2:]):
            return "down"
        fails = sum(1 for ok, _ in recent if not ok)
        rtts = [rtt for ok, rtt in recent if ok]
        if fails or (rtts and max(rtts) > 1200):
            return "weak"
        return "good"

    # ---------- packets ----------
    def _build(self, budget: int) -> Optional[dict]:
        inc = self.get_incident()
        rows = [(*row, False) for row in self.pending()] + [(*row, None, True) for row in self.withdrawals()]
        rows.sort(key=lambda row: (row[0], row[2]))
        if not rows:
            return None
        fields, removed, why = {}, [], []
        for _prio, rationale, key, value, withdraw in rows:
            trial = dict(fields)
            trial_removed = [*removed]
            if withdraw:
                trial_removed.append(key)
            else:
                trial[key] = value
            body = {"i": inc.id, "q": self.seq + 1, "tier": "critical", "f": trial,
                    "dest": (self.authorized or {}).get("destination"),
                    "x": len(rows) - len(trial) - len(trial_removed)}
            if trial_removed:
                body["rm"] = trial_removed
            if (fields or removed) and len(_compact(body)) > budget:
                break
            fields, removed = trial, trial_removed
            if rationale not in why:
                why.append(rationale)
            if len(_compact(body)) > budget:   # always send at least the top item
                break
        self.seq += 1
        packet = {"i": inc.id, "q": self.seq, "tier": "critical", "f": fields,
                  "dest": (self.authorized or {}).get("destination"),
                  "x": len(rows) - len(fields) - len(removed), "_why": why}
        if removed:
            packet["rm"] = removed
        return packet

    def _build_full(self) -> Optional[dict]:
        inc = self.get_incident()
        confirmed = [f for f in inc.facts if f.status.value == "confirmed"]
        if len(confirmed) == self.full_synced_facts:
            return None
        self.seq += 1
        timeline = [{"k": f.key, "v": f.value, "t": f.ts.isoformat(), "r": f.role.value, "s": f.speaker}
                    for f in confirmed]
        return {"i": inc.id, "q": self.seq, "tier": "full", "f": self.critical_values(), "tl": timeline,
                "dest": (self.authorized or {}).get("destination"), "x": 0, "_why": ["full record on a good link"],
                "_n": len(confirmed)}

    async def _maybe_probe(self) -> None:
        """Tiny reachability ping when idle, so the link state stays current and recovery is noticed."""
        if time.monotonic() - self.last_probe < 2.0:
            return
        self.last_probe = time.monotonic()
        t0 = time.perf_counter()
        try:
            if self._probe:
                await self._probe()
            elif self._transport:
                return                      # injected transports (tests) are not probed
            else:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as c:
                    (await c.get(f"{self.ed_url.rstrip('/')}/ping")).raise_for_status()
            self.results.append((True, (time.perf_counter() - t0) * 1000))
        except Exception:
            self.results.append((False, (time.perf_counter() - t0) * 1000))

    async def _send(self, packet: dict) -> dict:
        wire = _compact({k: v for k, v in packet.items() if not k.startswith("_")})
        if self._transport:
            return await self._transport(wire)
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.post(f"{self.ed_url.rstrip('/')}/ingest", content=wire,
                             headers={"Content-Type": "application/json"})
            r.raise_for_status()
            return r.json()

    async def tick(self) -> Optional[dict]:
        """One relay step. Returns the log entry, or None if nothing to do."""
        if not (self.configured and self.authorized):
            return None
        state = self.link_state()
        if self.inflight is None:
            # Until the link has been measured, assume it is weak: critical facts first, small packets.
            budget = self.tiers.budget["good"] if state == "good" else self.tiers.budget["weak"]
            pkt = self._build(budget)
            if pkt is None and state == "good":
                pkt = self._build_full()
            if pkt is None:
                await self._maybe_probe()
                return None
            self.inflight = pkt
        else:
            self.retries += 1
        pkt = self.inflight
        wire_len = len(_compact({k: v for k, v in pkt.items() if not k.startswith("_")}))
        t0 = time.perf_counter()
        entry = {"ts": utcnow().isoformat(), "seq": pkt["q"], "tier": pkt["tier"], "bytes": wire_len,
                 "keys": list(pkt["f"].keys()), "removed": pkt.get("rm", []), "why": pkt["_why"],
                 "queued_after": pkt["x"]}
        try:
            ack = await self._send(pkt)
            rtt = (time.perf_counter() - t0) * 1000
            if ack.get("ack") != pkt["q"]:
                raise RuntimeError(f"bad ack {ack}")
            self.results.append((True, rtt))
            for k, v in pkt["f"].items():
                self.acked[k] = v
            for k in pkt.get("rm", []):
                self.acked.pop(k, None)
            if pkt["tier"] == "full":
                self.full_synced_facts = pkt["_n"]
            self.bytes_sent += wire_len
            self.packets_acked += 1
            self.last_ack_at = utcnow().isoformat()
            self.inflight = None
            entry.update(result="acked", rtt_ms=round(rtt))
        except Exception as e:
            self.results.append((False, (time.perf_counter() - t0) * 1000))
            entry.update(result="failed", error=str(e)[:120])
            # If the link got worse, drop the in-flight packet so the next one is rebuilt smaller.
            # Sequence numbers are never reused for different content; re-sent values are idempotent.
            if self.link_state() in ("weak", "down") and len(pkt["f"]) + len(pkt.get("rm", [])) > 1:
                self.inflight = None
        self.log.append(entry)
        return entry

    def status(self) -> dict:
        inc = self.get_incident()
        pend = self.pending() if self.authorized else []
        local_bytes = len(_compact([f.model_dump(mode="json") for f in inc.facts]))
        if self.audio_dir:
            try:
                local_bytes += sum(os.path.getsize(p) for p in Path(self.audio_dir).glob("*.wav"))
            except OSError:
                pass
        sync = {}
        for k in self.critical_values():
            if self.acked.get(k) == self.critical_values().get(k):
                sync[k] = "sent"
            else:
                sync[k] = "queued"
        return {
            "configured": self.configured, "ed_url": self.ed_url, "authorized": self.authorized,
            "link": self.link_state() if self.configured else "not configured",
            "pending": [{"key": k, "priority": p, "why": w} for p, w, k, _ in pend],
            "sync": sync, "bytes_sent": self.bytes_sent, "local_bytes": local_bytes,
            "kept_local_pct": round(100 * (1 - self.bytes_sent / local_bytes), 2) if local_bytes else 100.0,
            "packets_acked": self.packets_acked, "retries": self.retries, "last_ack_at": self.last_ack_at,
            "log": list(self.log)[-12:],
        }

    async def run_forever(self, on_change: Callable[[], Awaitable[None]]) -> None:
        while True:
            try:
                entry = await self.tick()
            except Exception:
                entry = None
            if entry:
                await on_change()
            await asyncio.sleep(0.4 if entry and entry.get("result") == "acked" else 1.0)
