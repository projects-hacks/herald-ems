"""The written handoff report (MIST for trauma, SBAR for medical calls) from confirmed facts: GET /api/handoff."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from . import get_ctx

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
