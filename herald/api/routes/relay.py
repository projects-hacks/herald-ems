"""Relay authorization and configuration, and the presenter's link-emulation control (demo only)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ...relay.netem import MODES
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")


class Authorize(BaseModel):
    destination: str


class RelayConfig(BaseModel):
    ed_url: Optional[str] = None


@router.post("/relay/authorize")
async def relay_authorize(body: Authorize, c=Depends(get_ctx), h=Depends(get_hub)):
    """The medic authorizes destination + scope once; in-scope updates then flow on their own."""
    c.relay.authorize(body.destination, c.pre_alert_scope())
    c.persist()
    await h.broadcast()
    return c.relay.status()


@router.post("/relay/config")
async def relay_config(body: RelayConfig, c=Depends(get_ctx), h=Depends(get_hub)):
    c.relay.set_ed_url(body.ed_url)
    c.persist()
    await h.broadcast()
    return c.relay.status()


@router.post("/netem/{mode}")
async def netem_mode(mode: str, c=Depends(get_ctx), h=Depends(get_hub)):
    """Presenter control for the emulated link (Toxiproxy). Not part of the product."""
    if mode not in MODES:
        raise HTTPException(400, "mode must be good, weak, or down")
    try:
        proxy = await run_in_threadpool(c.link.set_mode, mode)
    except Exception as e:
        raise HTTPException(503, f"toxiproxy not reachable: {e}")
    c.netem_mode = mode
    await h.broadcast()
    return {"mode": mode, "enabled": proxy.get("enabled"), "toxics": [t["name"] for t in proxy.get("toxics", [])]}
