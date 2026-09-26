"""The written handoff report (MIST for trauma, SBAR for medical calls) from confirmed facts: GET /api/handoff, and
POST /api/handoff/not-obtained (the medic marks a required item "unable to obtain")."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core import not_obtained as unobtainable
from ...core.incident import IncidentEnded
from . import check_current_patient, get_ctx, get_hub

router = APIRouter(prefix="/api")


@router.get("/handoff")
async def get_handoff(format: Optional[str] = None, c=Depends(get_ctx)):
    """The current incident's report. `format` (e.g. mist, medical) overrides the format chosen from the open
    checklists."""
    ids = [f["id"] for f in c.handoff.formats()]
    if format is not None and format not in ids:
        raise HTTPException(400, f"format must be one of {', '.join(ids)}")
    return c.handoff.build(c.incident, format)


@router.get("/handoff/fhir")
async def get_handoff_fhir(type: str = "document", format: Optional[str] = None, c=Depends(get_ctx)):
    """The current incident's handoff as a FHIR R4 Bundle. `type=document` (default): a FHIR document whose
    Composition sections are the report's MIST/SBAR sections (`format` as in /api/handoff), with Encounter, Device and
    Provenance. `type=collection`: the resources alone. Confirmed facts only, exactly like /api/handoff."""
    if type not in ("document", "collection"):
        raise HTTPException(400, "type must be document or collection")
    if type == "collection":
        return c.fhir.build(c.incident)
    ids = [f["id"] for f in c.handoff.formats()]
    if format is not None and format not in ids:
        raise HTTPException(400, f"format must be one of {', '.join(ids)}")
    return c.fhir_document.build(c.incident, format)


class NotObtained(BaseModel):
    key: str
    on: bool


@router.post("/handoff/not-obtained", dependencies=[Depends(check_current_patient)])
async def set_not_obtained(body: NotObtained, c=Depends(get_ctx), h=Depends(get_hub)):
    """Mark (on) or unmark a required item the medic could not obtain for the current patient. The report then reads
    "<label>: unable to obtain" instead of "not yet known", and the item stops being asked for; a later confirmed fact
    for the key wins. 422: not a vocabulary key (or "|"-joined vocabulary keys, as a checklist item names them);
    409: the key already has a confirmed value, or the incident has ended. Audit-logged; returns the report."""
    if not unobtainable.is_markable(body.key, c.vocab):
        raise HTTPException(422, f"{body.key!r} is not a known vocabulary key")
    try:
        changed = unobtainable.mark(c.incident, body.key, body.on)
    except IncidentEnded as e:
        raise HTTPException(409, str(e)) from None
    except unobtainable.NotObtainedRefused as e:
        raise HTTPException(409, str(e)) from None
    if changed:
        c.persist()
    await h.broadcast()
    return c.handoff.build(c.incident)
