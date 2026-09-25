"""Patient roster endpoints for mass-casualty incidents."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from . import get_ctx, get_hub

router = APIRouter(prefix="/api/patients")


class NewPatient(BaseModel):
    label: str

    @field_validator("label")
    @classmethod
    def nonempty_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("patient label must not be empty")
        return value


def roster_state(context) -> dict:
    return {"patients": context.roster.summaries(), "active_patient": context.incident.id}


@router.get("")
async def patients(context=Depends(get_ctx)):
    return roster_state(context)


@router.post("")
async def add_patient(body: NewPatient, context=Depends(get_ctx), hub=Depends(get_hub)):
    context.roster.add(body.label)
    await hub.broadcast()
    return context.full_state()


@router.post("/{patient_id}/activate")
async def activate_patient(patient_id: str, context=Depends(get_ctx), hub=Depends(get_hub)):
    try:
        context.roster.activate(patient_id)
    except KeyError:
        raise HTTPException(404, f"unknown patient '{patient_id}'") from None
    await hub.broadcast()
    return context.full_state()
