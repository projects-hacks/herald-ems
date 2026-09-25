"""HTTP routes, one module per resource. Each reads its dependencies from request.app.state."""
from fastapi import HTTPException, Request

from ..capture import CaptureService
from ..context import AppContext
from ..hub import Hub


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_capture(request: Request) -> CaptureService:
    expected = request.headers.get("x-herald-patient")
    if expected and expected != request.app.state.ctx.incident.id:
        raise HTTPException(409, "Patient changed; review before submitting again")
    return request.app.state.capture.for_incident()


def get_hub(request: Request) -> Hub:
    return request.app.state.hub
