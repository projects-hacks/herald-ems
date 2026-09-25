"""Egress policy (E1): what left this box, what was queued, and what was refused, with reasons."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from . import get_ctx

router = APIRouter(prefix="/api")


@router.get("/egress")
async def egress(c=Depends(get_ctx)):
    return c.egress.snapshot()
