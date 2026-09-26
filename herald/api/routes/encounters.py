"""Medic-controlled milestones and read-only retained encounters."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.incident import IncidentEnded
from ...core.schema import utcnow
from ..encounters import hand_over
from ..media import dispose_incident_media
from . import get_ctx, get_hub, require_current_patient

router = APIRouter(prefix="/api/encounters")


@router.post("/resume", dependencies=[Depends(require_current_patient)])
async def resume(c=Depends(get_ctx), h=Depends(get_hub)):
    try:
        c.incident.ensure_open()
    except IncidentEnded as exc:
        raise HTTPException(409, str(exc)) from None
    c.restored = False
    await h.broadcast()
    return c.full_state()


class Milestone(BaseModel):
    disposition: Optional[str] = None      # required to finish: config/dispositions.yaml id


def record_disposition(c, inc, disposition: Optional[str]) -> None:
    """The medic's choice of how the encounter ended; finishing without one is refused."""
    outcome = c.dispositions.get(disposition)
    if outcome is None:
        raise HTTPException(422, "Choose how this encounter ended before finishing it")
    if not outcome["transport"] and (inc.arrived_at or inc.transferred_at):
        raise HTTPException(409, "Arrival or transfer of care is recorded; this patient was transported by this unit")
    inc.disposition = outcome["id"]
    inc.audit_log.append({"at": utcnow().isoformat(), "action": "disposition", "value": outcome["id"], "actor": "medic"})


class Handover(BaseModel):
    destination: Optional[str] = None


@router.post("/current/handover", dependencies=[Depends(require_current_patient)])
async def handover(body: Optional[Handover] = None, c=Depends(get_ctx), h=Depends(get_hub)):
    """One tap at the hospital: arrive + transfer + freeze the report + end the call, and relay the frozen report."""
    try:
        hand_over(c, body.destination if body else None)
    except IncidentEnded as exc:
        raise HTTPException(409, str(exc)) from None
    c.persist()
    await h.broadcast()
    return c.full_state()


@router.post("/current/{action}", dependencies=[Depends(require_current_patient)])
async def milestone(action: str, body: Optional[Milestone] = None, c=Depends(get_ctx), h=Depends(get_hub)):
    if action not in ("arrive", "transfer", "finish"):
        raise HTTPException(404, "Unknown encounter action")
    inc = c.incident
    with inc.lock:
        if action == "finish":
            if inc.ended_at is None:
                record_disposition(c, inc, body.disposition if body else None)
            dispose_incident_media(inc, audio_dir=c.settings.audio_dir,
                                   photo_dir=c.settings.photo_dir, evidence_dir=c.evidence_dir)
        else:
            try:
                inc.ensure_open()
            except IncidentEnded as exc:
                raise HTTPException(409, str(exc)) from None
            if inc.disposition and not c.dispositions.transports(inc.disposition):
                raise HTTPException(409, "This encounter ended without transport")
            if action == "arrive" and inc.transferred_at:
                raise HTTPException(409, "Transfer of care is already recorded")
            field = "arrived_at" if action == "arrive" else "transferred_at"
            if getattr(inc, field) is None:
                at = utcnow()
                setattr(inc, field, at)
                inc.audit_log.append({"at": at.isoformat(), "action": action, "actor": "medic"})
    if action == "finish" and c.capture_agent:
        c.capture_agent.set_auto(False)
    c.persist()
    await h.broadcast()
    return c.full_state()


@router.get("")
async def history(c=Depends(get_ctx)):
    return {"encounters": c.encounter_history(), "persisted": c.persistence is not None}


@router.get("/{patient_id}")
async def retained(patient_id: str, c=Depends(get_ctx)):
    for roster, relay in [(c.roster, c.relay), *((call.roster, call.relay) for call in c.previous_calls)]:
        for inc in roster.incidents():
            if inc.id == patient_id:
                return {"incident": inc.snapshot()["incident"], "label": inc.patient_label,
                        "handoff": inc.handoff_final or c.handoff.build(inc), "frozen": inc.handoff_final is not None,
                        "handover": relay.handover_status(inc), "relay": relay.status()}
    raise HTTPException(404, "Retained encounter not found")
