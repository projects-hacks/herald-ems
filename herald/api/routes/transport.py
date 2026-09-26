"""The vehicle's position (from the medic tablet or a vehicle GPS) and the medic's choice of destination."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.incident import IncidentEnded
from ...core.schema import CapturedBy, FactIn, Provenance, Role, Status
from . import check_current_patient, get_ctx, get_hub

router = APIRouter(prefix="/api/transport")


class Position(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)
    at: Optional[datetime] = None


class Destination(BaseModel):
    facility: str                          # a county facility id (config/counties/<id>.json destinations.facilities)


@router.post("/position")
async def position(body: Position, c=Depends(get_ctx), h=Depends(get_hub)):
    """Where the vehicle is. Kept in memory for routing only: never stored with the record or sent to the ED."""
    if c.transport is None:
        raise HTTPException(503, "Transport is not available")
    before = c.transport.view(c.incident, None)["options"]
    await c.transport.update_position(body.lat, body.lon, body.accuracy_m, body.at)
    if c.transport.view(c.incident, None)["options"] != before:
        await h.broadcast()                # only when a drive time changed, not on every fix
    return {"ok": True}


@router.post("/destination", dependencies=[Depends(check_current_patient)])
async def destination(body: Destination, c=Depends(get_ctx), h=Depends(get_hub)):
    """The medic's tap on a county hospital is the destination: written confirmed, replacing a heard or earlier
    value (which stays in the audit trail)."""
    facility = next((f for f in c.transport.options() if f.id == body.facility), None) if c.transport else None
    if facility is None:
        raise HTTPException(404, f"unknown facility '{body.facility}'")
    inc = c.incident
    try:
        current = inc.latest("transport.destination")
        if current is not None:
            fact = inc.correct(current.id, facility.name)
        else:
            fact = inc.ingest(FactIn(key="transport.destination", value=facility.name, role=Role.medic, speaker="medic",
                                     captured_by=CapturedBy.medic, confidence=1.0,
                                     provenance=Provenance(extractor="medic:destination-list")))
            fact = inc.set_status(fact.id, Status.confirmed)
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e)) from None
    c.persist()
    await h.broadcast()
    return fact.model_dump(mode="json")
