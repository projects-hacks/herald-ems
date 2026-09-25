"""The incident: start one, read the state, confirm, reject or correct a fact."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.incident import IncidentEnded
from ...core.schema import Status
from . import get_capture
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")
ACTIONS = {"confirm": Status.confirmed, "reject": Status.rejected}


class NewIncident(BaseModel):
    dispatch: Optional[str] = None


class Correction(BaseModel):
    value: Any


class BulkConfirm(BaseModel):
    ids: list[str]


@router.post("/incident")
async def new_incident(body: NewIncident, c=Depends(get_ctx), h=Depends(get_hub)):
    previous_cleanup = c.end_incident()
    c.new_incident(body.dispatch)
    c.relay.reset()
    c.persist()
    await h.broadcast()
    return {**c.full_state(), "previous_call_cleanup": previous_cleanup}


@router.post("/incident/end")
async def end_incident(c=Depends(get_ctx), h=Depends(get_hub)):
    cleanup = c.end_incident()
    await h.broadcast()
    return cleanup


@router.get("/state")
async def get_state(c=Depends(get_ctx)):
    return c.full_state()


@router.post("/facts/{fact_id}/correct")
async def correct_fact(fact_id: str, body: Correction, cap=Depends(get_capture)):
    """Replace a fact without rewriting history; the medic's save action is the explicit confirmation."""
    try:
        return await cap.correct(fact_id, body.value)
    except KeyError:
        raise HTTPException(404, "Fact not found in this incident")
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/facts/{fact_id}/{action}")
async def fact_action(fact_id: str, action: str, c=Depends(get_ctx), h=Depends(get_hub)):
    if action not in ACTIONS:
        raise HTTPException(400, "action must be confirm or reject")
    try:
        f = c.incident.set_status(fact_id, ACTIONS[action])
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(409, str(e))
    c.persist()
    await h.broadcast()
    return f.model_dump(mode="json")


class Spo2Scale(BaseModel):
    scale: int


@router.post("/patient/spo2-scale")
async def set_spo2_scale(body: Spo2Scale, c=Depends(get_ctx), h=Depends(get_hub)):
    """The one-tap NEWS2 SpO2 target switch: Scale 1 (94-98%) or Scale 2 (88-92%, hypercapnic respiratory failure).

    RCP: Scale 2 is used only under the direction of a qualified clinician. That is why patient.spo2_scale is
    require_tap and never taken from speech -- and why this tap, made by the medic on this screen, IS that direction:
    the fact is written confirmed in the same step, instead of asking for a second tap to confirm the first. The switch
    is recorded in the audit log, and switching back is the same one tap. It changes how SpO2 is coloured on the
    screen (config/vital_ranges.yaml); it is not sent as a clinical instruction and recommends nothing."""
    if body.scale not in (1, 2):
        raise HTTPException(400, "scale must be 1 or 2")
    from ...core.schema import FactIn, Provenance, Role, CapturedBy
    try:
        f = c.incident.ingest(FactIn(key="patient.spo2_scale", value=body.scale, role=Role.medic, speaker="medic",
                                     captured_by=CapturedBy.medic, confidence=1.0,
                                     provenance=Provenance(extractor="medic:spo2-scale-switch")))
        f = c.incident.set_status(f.id, Status.confirmed)
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e))
    c.persist()
    await h.broadcast()
    return f.model_dump(mode="json")


@router.post("/readings/{frame_id}/confirm")
async def confirm_reading(frame_id: str, c=Depends(get_ctx), h=Depends(get_hub)):
    """Confirm one capture's batchable readings in a single tap (herald/core/corroboration.py).

    One monitor frame yields HR/BP/SpO2/RR at once; this confirms the whole reading as a set instead of
    four separate taps. A reading the corroboration rules flag as needing its own look (a jump past the
    plausible step, the first reading of a key, a held fact, an unresolved label mismatch or contradiction,
    or any non-batchable key/source) is left unconfirmed and reported back in `individual` with why.
    """
    try:
        c.incident.ensure_open()
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    facts = c.projector.batch.group(c.incident, frame_id)
    if not facts:
        raise HTTPException(404, "No unconfirmed reading for this frame")
    decisions = c.projector.batch.review(facts)
    confirmed = []
    for d in decisions:
        if d.batchable:
            c.incident.set_status(d.fact_id, Status.confirmed)
            confirmed.append(d.fact_id)
    individual = [d.as_row() for d in decisions if not d.batchable]
    if confirmed:
        c.persist()
        await h.broadcast()
    return {"frame_id": frame_id, "confirmed": confirmed, "individual": individual}


@router.post("/facts/confirm")
async def confirm_facts(body: BulkConfirm, c=Depends(get_ctx), h=Depends(get_hub)):
    """Confirm selected independent readings in one medic action.

    Held values and unresolved contradictions deliberately remain individual decisions.
    Unknown IDs are reported, rather than silently ignored, so a stale UI cannot imply
    that a value reached the ED when it did not.
    """
    try:
        c.incident.ensure_open()
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    wanted = list(dict.fromkeys(body.ids))
    by_id = {fact.id: fact for fact in c.incident.facts}
    confirmed, skipped = [], []
    for fact_id in wanted:
        fact = by_id.get(fact_id)
        if fact is None:
            skipped.append({"id": fact_id, "reason": "not found"})
        elif fact.status != Status.unconfirmed:
            skipped.append({"id": fact_id, "reason": f"already {fact.status.value}"})
        elif fact.provenance.hold_reason:
            skipped.append({"id": fact_id, "reason": "held fact requires individual review"})
        elif fact.verify and fact.verify.status == "mismatch" and not fact.verify.resolution:
            skipped.append({"id": fact_id, "reason": "label mismatch requires individual review"})
        elif fact.key in c.vocab.contradiction_keys and fact.previous_value is not None:
            skipped.append({"id": fact_id, "reason": "contradiction requires individual review"})
        else:
            c.incident.set_status(fact_id, Status.confirmed)
            confirmed.append(fact_id)
    if confirmed:
        c.persist()
        await h.broadcast()
    return {"confirmed": confirmed, "skipped": skipped}
