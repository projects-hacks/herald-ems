"""The incident: start one, read the state, confirm or reject a fact."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.schema import Status
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")
ACTIONS = {"confirm": Status.confirmed, "reject": Status.rejected}


class NewIncident(BaseModel):
    dispatch: Optional[str] = None


@router.post("/incident")
async def new_incident(body: NewIncident, c=Depends(get_ctx), h=Depends(get_hub)):
    c.new_incident(body.dispatch)
    c.relay.reset()
    await h.broadcast()
    return c.full_state()


@router.get("/state")
async def get_state(c=Depends(get_ctx)):
    return c.full_state()


@router.post("/facts/{fact_id}/{action}")
async def fact_action(fact_id: str, action: str, c=Depends(get_ctx), h=Depends(get_hub)):
    if action not in ACTIONS:
        raise HTTPException(400, "action must be confirm or reject")
    try:
        f = c.incident.set_status(fact_id, ACTIONS[action])
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(409, str(e))
    await h.broadcast()
    return f.model_dump(mode="json")
