"""The incident: start one, read the state, confirm or reject a fact."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.incident import IncidentEnded
from ...core.schema import Status
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")
ACTIONS = {"confirm": Status.confirmed, "reject": Status.rejected}


class NewIncident(BaseModel):
    dispatch: Optional[str] = None


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
    c.persist()
    await h.broadcast()
    return f.model_dump(mode="json")


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
        elif fact.key in c.vocab.contradiction_keys and fact.previous_value is not None:
            skipped.append({"id": fact_id, "reason": "contradiction requires individual review"})
        else:
            c.incident.set_status(fact_id, Status.confirmed)
            confirmed.append(fact_id)
    if confirmed:
        c.persist()
        await h.broadcast()
    return {"confirmed": confirmed, "skipped": skipped}
