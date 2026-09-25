"""FastAPI application factory: wires the context, the capture service, the WebSocket hub, and the routers.

Background work (speech-to-text warm-up, the relay loop, power sampling) starts in the lifespan, so building
the app has no side effects (tests construct it freely)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket

from .context import AppContext, build_context, wire_capture
from .hub import Hub
from .frontend import mount_frontend
from .routes import capture as capture_routes
from .routes import agentic_capture, handoff, incident, patients, protocols, relay, system


def create_app(ctx: Optional[AppContext] = None) -> FastAPI:
    ctx = ctx or build_context()
    hub = Hub(ctx.full_state)
    capture_service, frame_source = wire_capture(ctx, hub.broadcast)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx.capture_agent.start(frame_source)
        if ctx.settings.warm_stt:
            asyncio.get_running_loop().run_in_executor(None, getattr(ctx.stt, "warm", lambda: None))
        async def relay_changed():
            ctx.persist()
            await hub.broadcast()
        task = asyncio.create_task(ctx.relay.run_forever(relay_changed))
        ctx.telemetry.start()
        sync_task = None
        if ctx.knowledge is not None:
            ctx.knowledge.build_async()

            async def sync_loop():
                while True:
                    await asyncio.sleep(5)
                    if ctx.knowledge.ready and ctx.knowledge.sync.due():
                        result = await asyncio.get_running_loop().run_in_executor(None, ctx.knowledge.sync.run)
                        if result and result.get("updated"):
                            await hub.broadcast()
            sync_task = asyncio.create_task(sync_loop())
        yield
        await ctx.capture_agent.stop()
        task.cancel()
        if sync_task:
            sync_task.cancel()

    app = FastAPI(title="Herald", version="0.2.0", lifespan=lifespan)
    app.state.ctx, app.state.hub = ctx, hub
    app.state.capture = capture_service
    for module in (incident, patients, capture_routes, relay, system, protocols, handoff, agentic_capture):
        app.include_router(module.router)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await hub.serve(ws)

    mount_frontend(app, ctx.settings.root)
    return app
