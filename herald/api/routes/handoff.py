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
