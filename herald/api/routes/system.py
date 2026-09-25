"""System endpoints: health, telemetry, the AI stack, the UI contract, and county configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...config import load_yaml
from ...telemetry.memory import memory_health
from . import get_ctx, get_hub

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(c=Depends(get_ctx)):
    """`*_available` is whether the model server is actually serving that label right now (the header's model chip)."""
    return {"llm_model": c.text_model.model_name(), "llm_available": await run_in_threadpool(c.text_model.available),
            "vision_model": c.vision_model.model_name(),
            "vision_available": await run_in_threadpool(c.vision_model.available),
            "stt_model": c.stt.model, "stt_loaded": c.stt.ready(),
            "incident": c.incident.id, "county": c.counties.active["id"],
            "cloud_ai_calls": c.egress.snapshot()["cloud_ai_calls"],
            "terminology": {"rxnorm_release": c.coder.release} if c.coder else None,
            "memory": await run_in_threadpool(memory_health, c.settings.memguard_status, c.settings.memguard_stale_s)}


@router.get("/telemetry")
async def telemetry(c=Depends(get_ctx)):
    """Tokens, tok/s, GPU watts, energy, and $ vs a cloud equivalent, with the assumptions stated."""
    jobs = ({"extraction": c.text_model.model_name(), "photos": c.vision_model.model_name(),
             "knowledge": c.knowledge_model.model_name()} if c.settings.knowledge_model else None)
    snap = await run_in_threadpool(c.telemetry.snapshot, c.text_model.model_name(), jobs)
    # E1: the measured decision (herald/egress/policy.py), not a literal -- telemetry/collector.py has no
    # network-policy dependency of its own, so the composition root fills this in, as system.py's routes do.
    egress_snapshot = c.egress.snapshot()
    snap["cloud_ai_calls"] = egress_snapshot["cloud_ai_calls"]
    snap["cloud_calls_refused"] = egress_snapshot["cloud_calls_refused"]
    # E3: bytes kept on this box, per open incident (herald/relay/relay.py `_incident_local_bytes`) -- the other
    # half of the defensibility story next to energy: not just cheaper inference, less ever leaves the vehicle.
    relay_status = c.relay.status()
    snap["local_bytes"] = relay_status["local_bytes"]
    snap["local_bytes_by_patient"] = {pid: row["local_bytes"] for pid, row in relay_status["patients"].items()}
    return snap


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
    out = {"models": models, "services": cfg["services"],
           "summary": f"{len(models)} models · {len(cfg['services'])} services",
           "cloud_ai_calls": c.egress.snapshot()["cloud_ai_calls"]}
    # Split stack only (TRAINING_PLAN §7a): name the model doing each job, so the demo and the deck show the split
    # honestly instead of implying one model does everything. Added only when the split is actually configured, so the
    # single-model response stays exactly as it was.
    if c.settings.knowledge_model:
        out["jobs"] = {"extraction": c.text_model.model_name(), "photos": c.vision_model.model_name(),
                       "knowledge": c.knowledge_model.model_name()}
    return out


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
    if c.knowledge is not None:
        c.knowledge.build_async()          # protocol lookup follows the county
    await h.broadcast()
    return c.counties.summary()
