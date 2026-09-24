"""Protocol lookup (P9): the county's own text with citations, page images, sync, and review confirmation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from ...knowledge.sync import ProtocolSync
from . import get_ctx, get_hub

router = APIRouter(prefix="/api/protocols")


def _kb(c):
    if c.knowledge is None:
        raise HTTPException(404, "protocol lookup is off (HERALD_KNOWLEDGE=0)")
    if not c.knowledge.ready:
        raise HTTPException(503, c.knowledge.status())
    return c.knowledge.kb


@router.get("")
async def protocols(c=Depends(get_ctx)):
    if c.knowledge is None:
        raise HTTPException(404, "protocol lookup is off (HERALD_KNOWLEDGE=0)")
    st = c.knowledge.status()
    if st.get("ready"):
        st["destination_audit"] = c.knowledge.kb.audit_destinations()
    return st


@router.get("/search")
async def search(q: str, k: int = 5, c=Depends(get_ctx)):
    """Answers are the county's own passages (document, section, page, effective date); a local model only chooses."""
    kb = _kb(c)
    return await run_in_threadpool(kb.answer, q, k)


@router.get("/{doc_id}/page/{page}")
async def page_image(doc_id: str, page: int, c=Depends(get_ctx)):
    kb = _kb(c)
    if doc_id not in kb.versions:
        raise HTTPException(404)
    png = await run_in_threadpool(kb.page_image, doc_id, page, c.settings.protocols_dir / "_pages")
    return FileResponse(png, media_type="image/png")


@router.post("/sync")
async def sync_now(c=Depends(get_ctx), h=Depends(get_hub)):
    _kb(c)
    result = await run_in_threadpool(c.knowledge.sync.run, True)
    await h.broadcast()
    return result


@router.post("/{doc_id}/reviewed")
async def mark_reviewed(doc_id: str, c=Depends(get_ctx), h=Depends(get_hub)):
    """A person confirms they checked the county config against the new document version."""
    kb = _kb(c)
    try:
        entry = ProtocolSync.mark_reviewed(kb, doc_id)
    except KeyError:
        raise HTTPException(404, f"no synced version of {doc_id}")
    await h.broadcast()
    return entry
