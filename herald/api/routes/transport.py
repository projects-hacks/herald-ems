"""The vehicle's position (from the medic tablet or a vehicle GPS) and the medic's tap on a destination: accepting
Herald's suggestion, or the rare pick from the county list."""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.incident import IncidentEnded
from ...core.schema import CapturedBy, FactIn, Provenance, Role
from ...transport.service import KEY, LISTED, SUGGESTED
from . import check_current_patient, get_ctx, get_hub

router = APIRouter(prefix="/api/transport")


class Position(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)
    at: Optional[datetime] = None
    # how old the fix is, measured on the device itself: immune to a tablet clock that differs from this box's
    age_s: Optional[float] = Field(default=None, ge=0, le=86400)


class Destination(BaseModel):
    facility: str                          # a county facility id (config/counties/<id>.json destinations.facilities)
    via: Literal["suggestion", "list"] = "list"


@router.post("/position")
async def position(body: Position, c=Depends(get_ctx), h=Depends(get_hub)):
    """Where the vehicle is. Kept in memory for routing only: never stored with the record or sent to the ED."""
    if c.transport is None:
        raise HTTPException(503, "Transport is not available")
    before = c.transport.rows()
    await c.transport.update_position(body.lat, body.lon, body.accuracy_m, body.at, body.age_s)
    if c.transport.rows() != before:
        await h.broadcast()                # only when a drive time changed, not on every fix
    return {"ok": True}


@router.post("/destination", dependencies=[Depends(check_current_patient)])
async def destination(body: Destination, c=Depends(get_ctx), h=Depends(get_hub)):
    """The medic's tap on a county hospital (Herald's suggestion, or one from the list) is the destination: written
    confirmed, replacing a heard or earlier value (which stays in the audit trail)."""
    facility = c.transport.by_id(body.facility) if c.transport else None
    if facility is None:
        raise HTTPException(404, f"unknown facility '{body.facility}'")
    inc = c.incident
    accepted = body.via == "suggestion"
    fin = FactIn(key=KEY, value=facility.name, role=Role.medic, speaker="medic", captured_by=CapturedBy.medic,
                 confidence=1.0, provenance=Provenance(
                     extractor=SUGGESTED if accepted else LISTED,
                     text="accepted Herald's suggestion" if accepted else "chosen from the county list"))
    try:
        current = inc.latest(KEY)
        fact = inc.settle(current.id if current else None, fin, actor="medic")
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e)) from None
    c.persist()
    await h.broadcast()
    return fact.model_dump(mode="json")
