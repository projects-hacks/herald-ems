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
from ..egress import EgressPolicy
from ..scoring import ScaleRegistry, default_scales
from .handover import final_report_body, handover_status, is_handed_over
from .tiers import RelayScopes, RelayTiers, default_scopes, default_tiers


def _compact(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), default=str).encode()


def _kept_local_pct(bytes_sent: int, bytes_without_relay: int) -> float:
    """Percentage of the uncompressed local record that the relay avoided sending."""
    if bytes_without_relay <= 0:
        return 100.0
    return round(max(0.0, min(100.0, 100 * (1 - bytes_sent / bytes_without_relay))), 2)


class Relay:
    def __init__(self, incident_getter: Callable, ed_url: Optional[str] = None,
                 transport: Optional[Transport] = None, probe: Optional[Callable[[], Awaitable[None]]] = None,
                 tiers: Optional[RelayTiers] = None, scales: Optional[ScaleRegistry] = None,
                 audio_dir: Optional[Path] = None, egress: Optional[EgressPolicy] = None,
                 ed_token: Optional[str] = None, scopes: Optional[RelayScopes] = None):
        self.get_incident = incident_getter
        self.ed_url = ed_url
        self.tiers = tiers or default_tiers()
        self.scopes = scopes or default_scopes()
        self.scales = scales or default_scales()
        self.audio_dir = audio_dir
        self.egress = egress    # E1: the real network path (below) always checks this before a packet leaves
        self.ed_token = ed_token  # B7: sent as X-Herald-Token; must match the receiver's own ED_RECEIVER_TOKEN
        self._transport = transport
        self._probe = probe
        self.last_probe = 0.0
        self.reset()

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"X-Herald-Token": self.ed_token} if self.ed_token else {}
        return {**h, **(extra or {})}

    def reset(self) -> None:
        self.authorized: Optional[dict] = None
        self.acked: dict[str, dict[str, Any]] = {}  # patient id -> values the ED acknowledged
        self.seq = 0
        self.inflight: Optional[dict] = None     # packet being retried (same seq until acked)
        self.results: deque = deque(maxlen=8)    # (ok, rtt_ms)
        self.log: deque = deque(maxlen=40)
        self.bytes_sent = 0
        self.packets_acked = 0
        self.retries = 0
        self.duplicates_acked = 0  # the ED told us it already had this sequence number (P3.2 reconciliation count)
        self.full_synced_facts: dict[str, int] = {}
        self.last_ack_at: Optional[str] = None
        self.clinician_acknowledgements: dict[str, list[dict]] = {}
        self.handovers: dict[str, dict] = {}    # patient id -> {"q", "delivered_at"}: the acked final packet

    # ---------- configuration ----------
    @property
    def configured(self) -> bool:
        return bool(self.ed_url or self._transport)

    def authorize(self, destination: str, scope: str = "patient update set", alert_ids: tuple = ()) -> None:
        """`scope` is the medic-facing label (`herald/api/context.py` `pre_alert_scope`); `alert_ids` is the
        machine scope actually enforced below (`config/relay.yaml` `scopes`). Neither is caller-provided free text
        the client can widen: the one HTTP caller always derives both from the checklists currently open."""
        self.authorized = {"destination": destination, "scope": scope, "at": utcnow().isoformat(),
                           "alert_ids": list(alert_ids)}

    def set_ed_url(self, ed_url: Optional[str]) -> None:
        """Point at a new receiver without carrying that receiver's acknowledgements over.

        Authorization remains a medic action, but an acknowledgement is only meaningful for
        the receiver that sent it.  Clearing this state makes the next tick resend the
        current critical values to the newly configured ED.
        """
        if self.ed_url == ed_url:
            return
        self.ed_url = ed_url
        self.acked.clear()
        self.full_synced_facts.clear()
        self.inflight = None
        self.last_ack_at = None
        self.clinician_acknowledgements.clear()
        self.handovers.clear()

    # ---------- what the ED should know ----------
    def _incidents(self) -> list:
        source = self.get_incident()
        if isinstance(source, dict):
            return list(source.values())
        if isinstance(source, (list, tuple, set)):
            return list(source)
        return [source]

    def _triage(self, inc) -> str:
        fact = inc.latest("triage.category", confirmed_only=True)
        return str(fact.value).lower() if fact else "unknown"

    def _triage_rank(self, inc) -> int:
        return self.tiers.triage_rank.get(self._triage(inc), self.tiers.triage_rank["unknown"])

    def _allowed_keys(self) -> Optional[frozenset[str]]:
        """None means unrestricted (no authorization yet: this only feeds the pre-authorization status preview,
        never a sent packet -- `tick()` refuses to send anything until `self.authorized` is set)."""
        if not self.authorized:
            return None
        return self.scopes.allowed_keys(self.authorized.get("alert_ids", []), self.tiers)

    def critical_values(self, inc=None) -> dict[str, Any]:
        inc = inc or self._incidents()[0]
        vals = inc.values(confirmed_only=True)
        allowed = self._allowed_keys()
        out = {k: v for k, v in vals.items() if k in self.tiers and (allowed is None or k in allowed)}
        snap = inc.snapshot()                  # scores from confirmed facts, for the active county only
        for sid, r in snap["scores"].items():
            key = f"score.{sid}"
            if (sid in self.scales and key in self.tiers and (allowed is None or key in allowed)
                    and (text := self.scales[sid].relay_text(r))):
                out[key] = text
        if snap["readiness"] and (allowed is None or "alert.readiness" in allowed):
            out["alert.readiness"] = "; ".join(
                f'{a["label"]} {a["done"]}/{a["total"]}{" ready" if a["ready"] else ""}'
                for a in snap["readiness"]
            )
        return out

    def pending(self) -> list[tuple[int, int, str, str, Any, Any]]:
        rows = []
        for inc in self._incidents():
            cur = self.critical_values(inc)
            acked = self.acked.get(inc.id, {})
            rows.extend((self._triage_rank(inc), *self.tiers.priority[k], k, v, inc)
                        for k, v in cur.items() if acked.get(k) != v)
        return sorted(rows, key=lambda r: (r[0], r[1], r[3]))

    def withdrawals(self) -> list[tuple[int, int, str, str, Any]]:
        """Per-patient values the ED acknowledged but the medic subsequently withdrew."""
        rows = []
        for inc in self._incidents():
            current = self.critical_values(inc)
            acked = self.acked.get(inc.id, {})
            rows.extend((self._triage_rank(inc), *self.tiers.priority[key], key, inc)
                        for key in acked if key not in current and key in self.tiers)
        return sorted(rows, key=lambda row: (row[0], row[1], row[3]))

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
        rows = [(*row, False) for row in self.pending()]
        rows += [(rank, priority, rationale, key, None, inc, True)
                 for rank, priority, rationale, key, inc in self.withdrawals()]
        rows.sort(key=lambda row: (row[0], row[1], row[3]))
        if not rows:
            return None
        inc = rows[0][5]
        patient_rows = [row for row in rows if row[5].id == inc.id]
        fields, removed, why = {}, [], []
        for _rank, _prio, rationale, key, value, _inc, withdraw in patient_rows:
            trial = dict(fields)
            trial_removed = [*removed]
            if withdraw:
                trial_removed.append(key)
            else:
                trial[key] = value
            body = {"i": inc.id, "q": self.seq + 1, "tier": "critical", "f": trial,
                    "patient": inc.patient_label, "dest": (self.authorized or {}).get("destination"),
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
                  "patient": inc.patient_label, "dest": (self.authorized or {}).get("destination"),
                  "x": len(rows) - len(fields) - len(removed), "_why": why}
        if removed:
            packet["rm"] = removed
        return packet

    def _build_full(self) -> Optional[dict]:
        candidates = []
        for order, inc in enumerate(self._incidents()):
            confirmed = [f for f in inc.facts if f.status.value == "confirmed"]
            if len(confirmed) != self.full_synced_facts.get(inc.id, 0):
                candidates.append((self._triage_rank(inc), order, inc, confirmed))
        if not candidates:
            return None
        _, _, inc, confirmed = min(candidates, key=lambda row: (row[0], row[1]))
        self.seq += 1
        timeline = [{"k": f.key, "v": f.value, "t": f.ts.isoformat(), "r": f.role.value, "s": f.speaker,
                     **({"o": f.provenance.observed_at.isoformat()} if f.provenance.observed_at else {})}
                    for f in confirmed]
        lkw = next((clock["since"] for clock in inc.snapshot()["clocks"]
                    if clock["id"] == "lkw" and clock.get("confirmed")), None)
        return {"i": inc.id, "q": self.seq, "tier": "full", "f": self.critical_values(inc), "tl": timeline,
                **({"lkw_at": lkw} if lkw else {}),
                "patient": inc.patient_label, "dest": (self.authorized or {}).get("destination"), "x": 0,
                "_why": ["full record on a good link"],
                "_n": len(confirmed)}

    def _build_handover(self) -> Optional[dict]:
        """The final "handed over" packet for the first handed-over patient the ED has not acknowledged it for.
        It carries no fields, so a failed send keeps it in flight and retries it with the same sequence number."""
        inc = next((inc for inc in self._incidents() if is_handed_over(inc) and inc.id not in self.handovers), None)
        if inc is None:
            return None
        self.seq += 1
        return {"i": inc.id, "q": self.seq, "tier": "handover", "f": {}, "ho": final_report_body(inc),
                "patient": inc.patient_label, "dest": (self.authorized or {}).get("destination"), "x": 0,
                "_why": ["final handoff report at hand over"]}

    def handover_status(self, inc) -> Optional[dict]:
        return handover_status(inc, self.handovers.get(inc.id), self.clinician_acknowledgements.get(inc.id, []))

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
                if self.egress:
                    decision = self.egress.decide(self.ed_url, purpose="relay:probe", link_state=self.link_state())
                    if decision.action != "allow":
                        raise RuntimeError(f"egress policy: {decision.reason}")
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as c:
                    (await c.get(f"{self.ed_url.rstrip('/')}/ping", headers=self._headers())).raise_for_status()
                    state_response = await c.get(f"{self.ed_url.rstrip('/')}/state", headers=self._headers())
                    state_response.raise_for_status()
                    state = state_response.json()
                    self.clinician_acknowledgements = {
                        patient_id: row.get("acknowledgements", [])
                        for patient_id, row in state.get("incidents", {}).items()
                    }
            self.results.append((True, (time.perf_counter() - t0) * 1000))
        except Exception:
            self.results.append((False, (time.perf_counter() - t0) * 1000))

    async def _send(self, packet: dict) -> dict:
        wire = _compact({k: v for k, v in packet.items() if not k.startswith("_")})
        if self._transport:
            return await self._transport(wire)
        if self.egress:
            decision = self.egress.decide(self.ed_url, purpose="relay:packet", link_state=self.link_state())
            if decision.action != "allow":
                raise RuntimeError(f"egress policy: {decision.reason}")
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.post(f"{self.ed_url.rstrip('/')}/ingest", content=wire,
                             headers=self._headers({"Content-Type": "application/json"}))
            r.raise_for_status()
            return r.json()

    async def tick(self, before_send: Optional[Callable] = None) -> Optional[dict]:
        """One relay step. Returns the log entry, or None if nothing to do."""
        if not (self.configured and self.authorized):
            return None
        state = self.link_state()
        if self.inflight is None:
            # Until the link has been measured, assume it is weak: critical facts first, small packets.
            budget = self.tiers.budget["good"] if state == "good" else self.tiers.budget["weak"]
            pkt = self._build(budget)
            if pkt is None:
                pkt = self._build_handover()   # after the latest critical values, before the full record
            if pkt is None and state == "good":
                pkt = self._build_full()
            if pkt is None:
                await self._maybe_probe()
                return None
            self.inflight = pkt
        else:
            self.retries += 1
        pkt = self.inflight
        if before_send:
            before_send()  # persist the allocated sequence and retry packet before it can reach the ED
        wire_len = len(_compact({k: v for k, v in pkt.items() if not k.startswith("_")}))
        t0 = time.perf_counter()
        entry = {"ts": utcnow().isoformat(), "seq": pkt["q"], "patient": pkt["i"],
                 "tier": pkt["tier"], "bytes": wire_len,
                 "keys": list(pkt["f"].keys()), "removed": pkt.get("rm", []),
                 "why": pkt["_why"], "queued_after": pkt["x"]}
        try:
            ack = await self._send(pkt)
            rtt = (time.perf_counter() - t0) * 1000
            if ack.get("ack") != pkt["q"]:
                raise RuntimeError(f"bad ack {ack}")
            if ack.get("duplicate"):
                self.duplicates_acked += 1
            self.results.append((True, rtt))
            patient_acked = self.acked.setdefault(pkt["i"], {})
            for k, v in pkt["f"].items():
                patient_acked[k] = v
            for k in pkt.get("rm", []):
                patient_acked.pop(k, None)
            if pkt["tier"] == "full":
                self.full_synced_facts[pkt["i"]] = pkt["_n"]
            if pkt["tier"] == "handover":
                self.handovers[pkt["i"]] = {"q": pkt["q"], "delivered_at": utcnow().isoformat()}
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

    def _incident_audio_bytes(self, inc) -> int:
        """This incident's own registered clips only (`inc.media_ids["audio"]`), not every .wav on disk."""
        if not self.audio_dir:
            return 0
        total = 0
        for audio_id in inc.media_ids.get("audio", ()):
            try:
                total += os.path.getsize(Path(self.audio_dir) / f"{audio_id}.wav")
            except OSError:
                continue
        return total

    def _incident_local_bytes(self, inc) -> int:
        """E3: what this one incident kept on this box -- its facts plus its own audio clips -- so the "kept
        local" story is defensible per patient, not just as one number across every open call."""
        return len(_compact([f.model_dump(mode="json") for f in inc.facts])) + self._incident_audio_bytes(inc)

    def status(self) -> dict:
        pend = self.pending() if self.authorized else []
        incidents = self._incidents()
        local_bytes_by_patient = {inc.id: self._incident_local_bytes(inc) for inc in incidents}
        local_bytes = sum(local_bytes_by_patient.values())
        patients = {}
        for inc in incidents:
            critical = self.critical_values(inc)
            acked = self.acked.get(inc.id, {})
            patients[inc.id] = {
                "triage": self._triage(inc),
                "pending": sum(1 for row in pend if row[5].id == inc.id),
                "sync": {key: "sent" if acked.get(key) == value else "queued"
                         for key, value in critical.items()},
                "local_bytes": local_bytes_by_patient[inc.id],
                "handover": self.handover_status(inc),
            }
        sync = patients[incidents[0].id]["sync"] if len(incidents) == 1 else {}
        return {
            "configured": self.configured, "ed_url": self.ed_url, "authorized": self.authorized,
            "link": self.link_state() if self.configured else "not configured",
            "pending": [{"patient": inc.id, "key": key, "priority": tier, "why": why}
                        for _rank, tier, why, key, _value, inc in pend],
            "patients": patients,
            "sync": sync, "bytes_sent": self.bytes_sent, "local_bytes": local_bytes,
            "kept_local_pct": _kept_local_pct(self.bytes_sent, local_bytes),
            "packets_acked": self.packets_acked, "retries": self.retries, "duplicates_acked": self.duplicates_acked,
            "last_ack_at": self.last_ack_at,
            "clinician_acknowledgements": self.clinician_acknowledgements,
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
