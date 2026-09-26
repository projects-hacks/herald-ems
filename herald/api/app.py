"""FastAPI application factory: wires the context, the capture service, the WebSocket hub, and the routers.

Background work (speech-to-text warm-up, the relay loop, power sampling) starts in the lifespan, so building
the app has no side effects (tests construct it freely)."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .auth import DeviceTokenMiddleware
from .context import AppContext, build_context, wire_capture
from .hub import Hub
from .routes import capture as capture_routes
from .routes import agentic_capture, egress, handoff, incident, patients, protocols, relay, system, encounters, transport


log = logging.getLogger("herald")


def preload_stt(stt) -> None:
    """HERALD_STT_PRELOAD=1: load and warm Whisper before the server accepts requests. The demo's speech memory is
    then claimed before anything else can take it, and a failed load stops startup instead of the first utterance."""
    t0 = time.monotonic()
    try:
        getattr(stt, "warm", lambda: None)()
    except Exception as e:
        raise RuntimeError(f"HERALD_STT_PRELOAD: speech-to-text failed to load: {type(e).__name__}: {e}") from e
    if not stt.ready():
        raise RuntimeError("HERALD_STT_PRELOAD: speech-to-text is not ready after loading")
    log.warning("speech-to-text preloaded in %.1f s", time.monotonic() - t0)


def create_app(ctx: Optional[AppContext] = None) -> FastAPI:
    ctx = ctx or build_context()
    hub = Hub(ctx.full_state)
    capture_service, frame_source = wire_capture(ctx, hub.broadcast)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx.capture_agent.start(frame_source)
        if ctx.settings.stt_preload:                       # demo: claim Whisper's memory now; fail loudly here
            preload_stt(ctx.stt)
        elif ctx.settings.warm_stt:
            asyncio.get_running_loop().run_in_executor(None, getattr(ctx.stt, "warm", lambda: None))
        async def relay_changed():
            ctx.persist()
            await hub.broadcast()
        from .encounters import relay_loop
        task = asyncio.create_task(relay_loop(ctx, relay_changed))
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
        cue_task = None
        if ctx.cues is not None:
            async def cue_loop():
                # the copilot looks up the county passage for each situation it recognises, off the request path
                loop = asyncio.get_running_loop()
                while True:
                    await asyncio.sleep(2)
                    if ctx.restored or ctx.incident.ended_at:
                        continue
                    try:
                        todo = ctx.cues.pending(ctx.incident.snapshot())
                    except Exception:
                        log.exception("protocol cues: could not read the situation")
                        continue
                    for cue in todo:
                        await loop.run_in_executor(None, ctx.cues.resolve, cue)
                        await hub.broadcast()
            cue_task = asyncio.create_task(cue_loop())
        match_task = None
        if ctx.transport is not None and ctx.transport.resolver is not None:
            async def match_loop():
                # a spoken destination is matched to the county list off the request path; the crew's words that
                # name one county hospital become the destination (herald/transport/service.py `settle`)
                loop = asyncio.get_running_loop()
                while True:
                    await asyncio.sleep(2)
                    inc = ctx.incident
                    if inc.ended_at:
                        continue
                    matched = False
                    for heard in ctx.transport.pending_matches(inc):
                        await loop.run_in_executor(None, ctx.transport.match, heard)
                        matched = True
                    try:
                        settled = ctx.transport.settle(inc) if inc is ctx.incident else None
                    except Exception as e:     # ended or changed meanwhile (IncidentEnded, a newer value): next pass
                        log.info("destination not settled: %s", e)
                        settled = None
                    if settled:
                        ctx.persist()
                    if matched or settled:
                        await hub.broadcast()
            match_task = asyncio.create_task(match_loop())
        yield
        if match_task:
            match_task.cancel()
        await ctx.capture_agent.stop()
        task.cancel()
        if sync_task:
            sync_task.cancel()
        if cue_task:
            cue_task.cancel()

    app = FastAPI(title="Herald", version="0.2.0", lifespan=lifespan)
    app.add_middleware(DeviceTokenMiddleware, token=ctx.settings.device_token)
    app.state.ctx, app.state.hub = ctx, hub
    app.state.capture = capture_service
    for module in (incident, encounters, patients, transport, capture_routes, relay, system, protocols, handoff, agentic_capture, egress):
        app.include_router(module.router)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await hub.serve(ws)

    # The React build at / when it exists (HERALD_UI=classic switches back); the original screen stays at /classic/.
    root = ctx.settings.root
    @app.get("/capture.html", include_in_schema=False)
    async def capture_page():
        return FileResponse(root / "web" / "capture.html")
    ui_dist = root / "ui" / "dist"
    use_new_ui = ctx.settings.ui == "new" and (ui_dist / "index.html").exists()
    app.mount("/classic", StaticFiles(directory=str(root / "web"), html=True), name="classic")
    app.mount("/", StaticFiles(directory=str(ui_dist if use_new_ui else root / "web"), html=True), name="web")
    return app
