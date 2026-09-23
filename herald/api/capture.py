"""Capture: speech, photos, and structured readings in; facts and a trace entry out.

Speech is two-phase: the rules result reaches the screen immediately, and the local model's additions follow
on the same trace entry. Every step is recorded (the "Herald thinking" card)."""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from fastapi.concurrency import run_in_threadpool

from ..core.schema import CapturedBy, FactIn, Role, new_id, utcnow
from ..extraction.pipeline import merge_model_facts
from .context import AppContext

Broadcast = Callable[[], Awaitable[None]]


class CaptureService:
    def __init__(self, ctx: AppContext, broadcast: Broadcast):
        self.ctx, self.broadcast = ctx, broadcast

    @property
    def inc(self):
        return self.ctx.incident

    def _summary(self) -> dict:
        return self.ctx.tracer.summarize(self.inc.snapshot())

    def ingest_batch(self, facts_in, rejected: Optional[list] = None) -> list:
        """Ingest what validates; anything implausible or malformed is listed in `rejected` for the trace."""
        facts = []
        for f in facts_in:
            try:
                facts.append(self.inc.ingest(f, record=False))
            except ValueError as e:
                if rejected is not None:
                    rejected.append({"key": f.key, "value": f.value, "reason": str(e)[:120]})
        self.inc.commit()
        return facts

    # ---------- speech ----------
    async def text(self, text: str, captured_by: CapturedBy, role: Optional[Role], speaker: Optional[str],
                   audio_id: Optional[str], use_model: bool, stt_info: Optional[dict] = None) -> dict:
        ctx, tracer = self.ctx, self.ctx.tracer
        default_role = role or (Role.medic if captured_by == CapturedBy.medic else Role.family)
        before = self._summary()
        t0 = time.perf_counter()
        rules_in = ctx.rules.extract(text, captured_by, default_role, speaker, audio_id)
        rules_ms = round((time.perf_counter() - t0) * 1000, 1)
        rejected: list = []
        facts = self.ingest_batch(rules_in, rejected)
        after = self._summary()
        injected = ctx.guard.match(text)
        model_on = use_model and ctx.text_model.available() and not injected
        entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": text, "captured_by": captured_by.value,
                 "speaker": speaker, "audio_id": audio_id, "fact_ids": [f.id for f in facts],
                 "extract": {"rules": len(facts), "llm": None, "ms": rules_ms}, "stt": stt_info,
                 "trace": {"heard": {"text": text, "speaker": speaker or captured_by.value, "audio_id": audio_id,
                                     "stt": stt_info},
                           "rules": {"ms": rules_ms, "facts": [tracer.fact_view(f) for f in facts], "rejected": rejected},
                           "model": ({"status": "running", "name": ctx.text_model.model_name()} if model_on else
                                     {"status": "skipped", "reason": f"instruction-shaped speech (\"{injected}\"): "
                                      "model output discarded for this utterance"} if injected else {"status": "off"}),
                           "guard": {"instruction_shaped": injected},
                           "effects": tracer.diff(before, after)}}
        self.inc.transcripts.append(entry)
        await self.broadcast()
        if model_on:
            asyncio.create_task(self._refine(entry, text, captured_by, default_role, speaker, audio_id, rules_in))
        return {"transcript": entry, "facts": [f.model_dump(mode="json") for f in facts]}

    async def _refine(self, entry: dict, text: str, captured_by: CapturedBy, default_role: Role,
                      speaker: Optional[str], audio_id: Optional[str], rules_in: list) -> None:
        ctx, tracer = self.ctx, self.ctx.tracer
        before = self._summary()
        t0 = time.perf_counter()
        name = ctx.text_model.model_name()
        try:
            model_in = await run_in_threadpool(ctx.model_extractor.extract, text, captured_by, default_role,
                                               speaker, audio_id)
            usage = ctx.model_extractor.last_usage or {}
            by_key = {f.key: f for f in rules_in}
            agreed = sum(1 for f in model_in if f.key in by_key
                         and str(by_key[f.key].value).lower() == str(f.value).lower())
            rejected: list = []
            added = self.ingest_batch(merge_model_facts(rules_in, model_in), rejected)
            entry["fact_ids"] += [f.id for f in added]
            entry["extract"]["llm"] = len(added)
            entry["trace"]["model"] = {"status": "done", "name": name, "ms": round((time.perf_counter() - t0) * 1000),
                                       "tokens": usage.get("completion_tokens"), "proposed": len(model_in),
                                       "facts": [tracer.fact_view(f) for f in added], "rejected": rejected,
                                       "agreed_with_rules": agreed,
                                       "overridden_by_rules": len(model_in) - len(added) - len(rejected) - agreed}
            eff = tracer.diff(before, self._summary())
            for k in ("readiness", "alerts_new", "scores", "gaps_closed"):
                entry["trace"]["effects"][k] = entry["trace"]["effects"].get(k, []) + eff[k]
        except Exception as e:
            entry["trace"]["model"] = {"status": "error", "name": name, "error": str(e)[:200],
                                       "ms": round((time.perf_counter() - t0) * 1000)}
        await self.broadcast()

    # ---------- photo ----------
    async def photo(self, raw: bytes, mode: str) -> dict:
        ctx, tracer = self.ctx, self.ctx.tracer
        photo_id = new_id("p")
        ctx.settings.photo_dir.mkdir(parents=True, exist_ok=True)
        (ctx.settings.photo_dir / f"{photo_id}.jpg").write_bytes(raw)
        before = self._summary()
        t0 = time.perf_counter()
        heard = {"text": f"photo ({mode.replace('_', ' ')})", "photo_id": photo_id}
        entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": f"[photo: {mode}]", "captured_by": "camera",
                 "speaker": mode, "audio_id": None, "photo_id": photo_id, "fact_ids": [],
                 "extract": {"rules": 0, "llm": 0, "ms": 0}}
        try:
            facts_in = await run_in_threadpool(ctx.vision.read, raw, mode, photo_id)
        except Exception as e:
            # The photo is kept and the failure recorded, so the NOW screen shows it (UX_PLAN §4.3 g).
            entry["trace"] = {"heard": heard, "rules": {"ms": 0, "facts": []},
                              "model": {"status": "error", "name": ctx.text_model.model_name(), "error": str(e)[:200],
                                        "ms": round((time.perf_counter() - t0) * 1000)},
                              "effects": tracer.diff(before, before)}
            self.inc.transcripts.append(entry)
            await self.broadcast()
            raise
        ms = round((time.perf_counter() - t0) * 1000)
        rejected: list = []
        facts = self.ingest_batch(facts_in, rejected)
        entry["fact_ids"] = [f.id for f in facts]
        entry["extract"] = {"rules": 0, "llm": len(facts), "ms": ms}
        entry["trace"] = {"heard": heard, "rules": {"ms": 0, "facts": []},
                          "model": {"status": "done", "name": ctx.text_model.model_name(), "ms": ms,
                                    "facts": [tracer.fact_view(f) for f in facts], "rejected": rejected},
                          "effects": tracer.diff(before, self._summary())}
        self.inc.transcripts.append(entry)
        await self.broadcast()
        return {"photo_id": photo_id, "facts": [f.model_dump(mode="json") for f in facts]}

    # ---------- structured readings (monitor panel, device feed) ----------
    async def structured(self, facts: list[FactIn]) -> list[dict]:
        """All-or-nothing: one invalid fact rejects the batch (ValueError). One trace entry per call."""
        tracer = self.ctx.tracer
        for f in facts:
            self.inc.validate(f)
        before = self._summary()
        added = [self.inc.ingest(f, record=False) for f in facts]
        self.inc.commit()
        if added:
            speaker = added[0].speaker or added[0].captured_by.value
            said = " · ".join(f"{self.ctx.vocab.label(f.key)} {f.value}" for f in added)
            self.inc.transcripts.append({
                "id": new_id("t"), "ts": utcnow().isoformat(), "text": f"[{speaker}] {said}",
                "captured_by": added[0].captured_by.value, "speaker": speaker, "audio_id": None,
                "fact_ids": [f.id for f in added], "extract": {"rules": 0, "llm": None, "ms": 0},
                "trace": {"heard": {"text": said, "speaker": speaker, "source": "structured"},
                          "rules": {"ms": 0, "facts": [tracer.fact_view(f) for f in added]},
                          "model": {"status": "off", "reason": "structured readings; nothing to extract"},
                          "guard": {"instruction_shaped": None},
                          "effects": tracer.diff(before, self._summary())}})
        await self.broadcast()
        return [f.model_dump(mode="json") for f in added]
