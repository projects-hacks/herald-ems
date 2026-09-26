"""Encrypted encounter recovery and delivery queues, independent of the active capture target."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from ..core.roster import PatientRoster
from ..core.incident import Incident
from ..core.schema import Fact
from ..relay import Relay

log = logging.getLogger(__name__)
RELAY_FIELDS = ("authorized", "acked", "ed_url", "seq", "inflight", "full_synced_facts",
                "last_ack_at", "clinician_acknowledgements", "bytes_sent", "packets_acked",
                "retries", "duplicates_acked")


@dataclass
class SavedCall:
    roster: PatientRoster
    relay: Relay


def fresh_relay(context, roster) -> Relay:
    previous = context.relay
    return Relay(roster.incidents, previous.ed_url, tiers=context.tiers, scales=context.scales,
                 audio_dir=context.settings.audio_dir, egress=context.egress,
                 ed_token=previous.ed_token, transport=previous._transport, probe=previous._probe, scopes=previous.scopes)


def encode_call(roster, relay) -> dict:
    patients = []
    for inc in roster.incidents():
        with inc.lock:
            patients.append({"id": inc.id, "label": inc.patient_label, "dispatch": inc.dispatch,
                             **{key: getattr(inc, key).isoformat() if getattr(inc, key) else None
                                for key in ("started", "ended_at", "arrived_at", "transferred_at")},
                             "facts": [f.model_dump(mode="json") for f in inc.facts],
                             "transcripts": inc.transcripts, "audit": inc.audit_log,
                             "news2": inc.news2_history, "media_disposal": inc.media_disposal,
                             "media_ids": {k: sorted(v) for k, v in inc.media_ids.items()},
                             "not_obtained": list(inc.not_obtained)})
    return {"active": roster.active_id, "patients": patients,
            "relay": {key: getattr(relay, key) for key in RELAY_FIELDS}}


def decode_call(context, payload: dict) -> SavedCall:
    dispatch = payload["patients"][0].get("dispatch")
    roster = PatientRoster(lambda: Incident(dispatch, vocabulary=context.vocab, policy=context.policy, projector=context.projector))
    for row in payload["patients"]:
        inc = roster._factory()
        inc.id, inc.patient_label, inc.dispatch = row["id"], row.get("label"), row.get("dispatch")
        for key in ("started", "ended_at", "arrived_at", "transferred_at"):
            setattr(inc, key, datetime.fromisoformat(row[key]) if row.get(key) else None)
        inc.facts = [Fact.model_validate(fact) for fact in row.get("facts", [])]
        inc.transcripts, inc.audit_log = row.get("transcripts", []), row.get("audit", [])
        inc.news2_history, inc.media_disposal = row.get("news2", []), row.get("media_disposal")
        inc.media_ids = {"audio": set(), "photo": set(), "evidence": set()} | {
            kind: set(ids) for kind, ids in row.get("media_ids", {}).items()}
        inc.not_obtained = list(row.get("not_obtained", []))
        roster._incidents[inc.id], roster._labels[inc.id] = inc, inc.patient_label
    roster.active_id = payload.get("active") if payload.get("active") in roster._incidents else next(iter(roster._incidents))
    relay = fresh_relay(context, roster)
    for key in RELAY_FIELDS:
        if key in payload.get("relay", {}):
            setattr(relay, key, payload["relay"][key])
    return SavedCall(roster, relay)


async def relay_loop(context, on_change):
    """A new call never retargets an old queue or interrupts its in-flight acknowledgment."""
    while True:
        # Snapshot the relays before awaiting: a transition may happen while one sends.
        relays = [context.relay, *(call.relay for call in context.previous_calls)]
        for relay in relays:
            try:
                receipts = relay.clinician_acknowledgements
                entry = await relay.tick(before_send=context.persist)
                if entry or receipts != relay.clinician_acknowledgements:
                    await on_change()
            except Exception:
                log.exception("Could not advance encounter delivery queue")
        await asyncio.sleep(0.4)
