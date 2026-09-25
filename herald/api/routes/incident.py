"""The incident: start one, read the state, confirm, reject or correct a fact."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.schema import Status
from . import get_capture
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")
ACTIONS = {"confirm": Status.confirmed, "reject": Status.rejected}


class NewIncident(BaseModel):
    dispatch: Optional[str] = None


class Correction(BaseModel):
    value: Any


@router.post("/incident")
async def new_incident(body: NewIncident, c=Depends(get_ctx), h=Depends(get_hub)):
    c.new_incident(body.dispatch)
    c.relay.reset()
    await h.broadcast()
    return c.full_state()


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
    except KeyError:
        raise HTTPException(404)
    await h.broadcast()
    return f.model_dump(mode="json")
