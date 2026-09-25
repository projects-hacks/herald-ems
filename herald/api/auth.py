"""Device token (B7): one shared secret every mutating /api/* request must present, when the deployment
configures one (HERALD_DEVICE_TOKEN, herald/config/settings.py). Unset = disabled, the local-dev default: every
request passes exactly as it did before this existed. GET requests, the WebSocket, and everything outside /api/
(the UI's static files) are never gated -- a tablet reading the live picture needs no secret, only writing to it
does. This is a shared-device deterrent against another device on the same LAN/tablet Wi-Fi mutating patient
state, not an authentication system: one token, no accounts, no expiry (docs/README §"Bind address and the
device token")."""
from __future__ import annotations

from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TOKEN_HEADER = "x-herald-token"


class DeviceTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: Optional[str]):
        super().__init__(app)
        self.token = token or None

    async def dispatch(self, request: Request, call_next):
        if (self.token and request.method in MUTATING_METHODS and request.url.path.startswith("/api/")
                and request.headers.get(TOKEN_HEADER) != self.token):
            return JSONResponse({"detail": "missing or invalid device token (X-Herald-Token)"}, status_code=401)
        return await call_next(request)
