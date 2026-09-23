"""System endpoints: health, telemetry, the AI stack, the UI contract, and county configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...config import load_yaml
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(c=Depends(get_ctx)):
    return {"llm_model": c.text_model.model_name(), "vision_model": c.vision_model.model_name(),
            "stt_model": c.stt.model, "stt_loaded": c.stt.ready(),
            "incident": c.incident.id, "county": c.counties.active["id"], "cloud_ai_calls": 0}


@router.get("/telemetry")
async def telemetry(c=Depends(get_ctx)):
    """Tokens, tok/s, GPU watts, energy, and $ vs a cloud equivalent, with the assumptions stated."""
    return await run_in_threadpool(c.telemetry.snapshot, c.text_model.model_name())


@router.get("/stack")
async def stack(c=Depends(get_ctx)):
    """The AI stack in HP's console terms: models (with live readiness) and intelligence services."""
    cfg = load_yaml("stack.yaml")
    served = {"text_model": c.text_model.model_name(), "vision_model": c.vision_model.model_name()}
    models = []
    for m in cfg["models"]:
        if m["component"] == "stt":
            status = "ready" if c.stt.ready() else "loading"
        else:
            now = served.get(m["component"])
            status = ("ready" if now == m.get("served_as") else
                      "not served" if now is None else f"not served (serving {now})")
        models.append({k: v for k, v in m.items() if k != "component"} | {"status": status})
    return {"models": models, "services": cfg["services"],
            "summary": f"{len(models)} models · {len(cfg['services'])} services", "cloud_ai_calls": 0}


@router.get("/meta")
async def meta(c=Depends(get_ctx)):
    """Labels, units, relay tiers, change rules, checklists and county (the UI contract)."""
    return c.contract.all()


@router.get("/county")
async def get_county(c=Depends(get_ctx)):
    """The active county configuration (stroke scales, checklist, destinations, protocol versions)."""
    return {"active": c.counties.active, "available": c.counties.available()}


@router.post("/county/{county_id}")
async def set_county(county_id: str, c=Depends(get_ctx), h=Depends(get_hub)):
    """Switch county live: the checklist, stroke scale and destinations change on every screen."""
    try:
        c.counties.activate(county_id)
    except KeyError:
        raise HTTPException(404, f"no county config '{county_id}'; available: {list(c.counties.available())}")
    await h.broadcast()
    return c.counties.summary()
