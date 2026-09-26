"""Relay authorization and configuration, and the presenter's link-emulation control (demo only)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ...relay.netem import MODES
from . import get_ctx, get_hub, check_current_patient

router = APIRouter(prefix="/api")


class Authorize(BaseModel):
    destination: str


class RelayConfig(BaseModel):
    ed_url: Optional[str] = None


@router.post("/relay/authorize", dependencies=[Depends(check_current_patient)])
async def relay_authorize(body: Authorize, c=Depends(get_ctx), h=Depends(get_hub)):
    """The medic authorizes destination + scope once; in-scope updates then flow on their own."""
    label, alert_ids = c.pre_alert_scope()
    receiver = c.receiver_for(body.destination)
    if receiver != c.relay.ed_url and receiver:
        c.relay.set_ed_url(receiver)             # this hospital's own receiving system (HERALD_ED_RECEIVERS)
    c.relay.authorize(body.destination, label, alert_ids)
    c.persist()
    await h.broadcast()
    return c.relay.status()


@router.post("/relay/config")
async def relay_config(body: RelayConfig, c=Depends(get_ctx), h=Depends(get_hub)):
    """B7: the ED URL is gated by the same egress policy every outbound call passes through (E1). A host that
    isn't this box's local model server and isn't on config/egress.yaml's allow-list (or this deployment's own
    HERALD_ED_URL/HERALD_PROTOCOL_MIRROR) is refused here, before it is ever stored or dialed."""
    if body.ed_url:
        decision = c.egress.decide(body.ed_url, purpose="relay:config")
        if decision.action == "deny":
            raise HTTPException(403, f"ED URL refused by egress policy: {decision.reason}")
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
