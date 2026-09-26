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
    if request.app.state.ctx.restored:
        raise HTTPException(409, "Confirm the restored patient before capturing")
    return request.app.state.capture.for_incident()


def get_hub(request: Request) -> Hub:
    return request.app.state.hub


def require_current_patient(request: Request) -> None:
    expected = request.headers.get("x-herald-patient")
    if not expected or expected != request.app.state.ctx.incident.id:
        raise HTTPException(409, "Review the current patient before changing encounters")


def check_current_patient(request: Request) -> None:
    """Older clients may omit the header; a supplied stale identity is never ignored."""
    if request.headers.get("x-herald-patient"):
        require_current_patient(request)
