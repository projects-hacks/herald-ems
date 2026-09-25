"""FastAPI application factory: wires the context, the capture service, the WebSocket hub, and the routers.

Background work (speech-to-text warm-up, the relay loop, power sampling) starts in the lifespan, so building
the app has no side effects (tests construct it freely)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from .capture import CaptureService
from .context import AppContext, build_context
from .hub import Hub
from .routes import capture as capture_routes
from .routes import handoff, incident, patients, protocols, relay, system


def create_app(ctx: Optional[AppContext] = None) -> FastAPI:
    ctx = ctx or build_context()
    hub = Hub(ctx.full_state)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        task.cancel()
        if sync_task:
            sync_task.cancel()

    app = FastAPI(title="Herald", version="0.2.0", lifespan=lifespan)
    app.state.ctx, app.state.hub = ctx, hub
    app.state.capture = CaptureService(ctx, hub.broadcast)
    for module in (incident, patients, capture_routes, relay, system, protocols, handoff):
        app.include_router(module.router)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await hub.serve(ws)

    # The React build at / when it exists (HERALD_UI=classic switches back); the original screen stays at /classic/.
    root = ctx.settings.root
    ui_dist = root / "ui" / "dist"
    use_new_ui = ctx.settings.ui == "new" and (ui_dist / "index.html").exists()
    app.mount("/classic", StaticFiles(directory=str(root / "web"), html=True), name="classic")
    app.mount("/", StaticFiles(directory=str(ui_dist if use_new_ui else root / "web"), html=True), name="web")
    return app
