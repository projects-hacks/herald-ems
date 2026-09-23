"""HTTP routes, one module per resource. Each reads its dependencies from request.app.state."""
from fastapi import Request

from ..capture import CaptureService
from ..context import AppContext
from ..hub import Hub


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_capture(request: Request) -> CaptureService:
    return request.app.state.capture


def get_hub(request: Request) -> Hub:
    return request.app.state.hub
