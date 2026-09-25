"""Capture: speech, photos, and structured readings in; facts and a trace entry out.

Speech is two-phase: the words reach the screen immediately, and the extraction model's facts follow on the
same trace entry. The model is the only extractor. `trace.rules` stays in the entry shape for the UI contract; for
speech and photos it is always empty, and it carries the monitor panel's readings. Every step is recorded (the
"Herald thinking" card)."""
from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Awaitable, Callable, Optional

from fastapi.concurrency import run_in_threadpool

from ..core.incident import IncidentEnded
from ..core.schema import CapturedBy, FactIn, Provenance, Role, join_reasons, new_id, source_role, utcnow
from ..capture.types import IncidentEvent
from .context import AppContext

Broadcast = Callable[[], Awaitable[None]]


class ModelUnavailable(RuntimeError):
    """The extraction model isn't serving: Herald does not extract without it."""


class CaptureService:
    def __init__(self, ctx: AppContext, broadcast: Broadcast):
        self.ctx, self.broadcast = ctx, broadcast
        self.listeners = []
        self._incident = None
        self.ambient = False

    def for_incident(self):
        scoped = CaptureService(self.ctx, self.broadcast)
        scoped._incident = self.ctx.incident
        scoped.listeners = self.listeners
        return scoped

    @property
    def inc(self):
        return self._incident if self._incident is not None else self.ctx.incident

    async def _saved_broadcast(self) -> None:
        self.ctx.persist()
        await self.broadcast()

    def notify(self, facts, before):
        if self.inc is not self.ctx.incident:
            return
        diff = self.ctx.tracer.diff(before, self._summary())
        events = [IncidentEvent("facts_added", facts, diff, self.inc.id)]
        if diff.get("alerts_new") and any(f.captured_by != CapturedBy.camera for f in facts):
            events.append(IncidentEvent("alert_new", facts, diff, self.inc.id))
        for fact in facts:
            if fact.key == "transport.eta_min":
                events.append(IncidentEvent("eta_changed", [fact], {"eta_min": fact.value}, self.inc.id))
        for event in events:
            for listener in self.listeners:
                listener.on_change(event)

    def _summary(self) -> dict:
        return self.ctx.tracer.summarize(self.inc.snapshot())

    def ingest_batch(self, facts_in, rejected: Optional[list] = None) -> list:
        """Ingest what validates; anything implausible or malformed is listed in `rejected` for the trace."""
        facts = []
        before = self._summary()
        for f in facts_in:
            if self.ambient:
                f.captured_by = CapturedBy.other
                f.role = Role.unknown
                f.speaker = "Ambient audio · speaker unverified"
                reason = "Ambient speech: verify the words, speaker, and patient before confirming"
                f.provenance.hold_reason = "; ".join(filter(None, [f.provenance.hold_reason, reason]))
            try:
                facts.append(self.inc.ingest(f, record=False))
            except ValueError as e:
                if rejected is not None:
                    rejected.append({"key": f.key, "value": f.value, "reason": str(e)[:120]})
        self.inc.commit()
        self.notify(facts, before)
        return facts

    # ---------- speech ----------
    async def text(self, text: str, captured_by: CapturedBy, role: Optional[Role], speaker: Optional[str],
                   audio_id: Optional[str], use_model: bool = True, stt_info: Optional[dict] = None) -> dict:
        """The words appear at once (the entry, model "running"); the model's facts follow on the same entry.
        There is no regex extraction: if the model is down, the words are kept as evidence and nothing is
        extracted (ModelUnavailable). Each fact confirms itself only if the confirmation policy allows it
        (the paramedic's own mic, confidence at or above the calibrated bar); everything else needs a tap."""
        ctx = self.ctx
        default_role = source_role(captured_by, speaker, role)
        injected = ctx.guard.match(text)
        skip = bool(injected) and ctx.settings.guard_policy == "skip_model"
        available = use_model and ctx.text_model.available()
        if not use_model:
            model = {"status": "off", "reason": "model extraction switched off for this request"}
        elif not available:
            model = {"status": "unavailable", "reason": "the extraction model is not running: nothing extracted "
                     "from these words (check `zrt status`)"}
        elif skip:
            model = {"status": "skipped", "reason": f'instruction-shaped speech ("{injected}"): model not run'}
        else:
            model = {"status": "running", "name": ctx.text_model.model_name()}
        entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": text, "captured_by": captured_by.value,
                 "speaker": speaker, "audio_id": audio_id, "fact_ids": [],
                 "extract": {"rules": 0, "llm": None, "ms": 0}, "stt": stt_info,
                 "trace": {"heard": {"text": text, "speaker": speaker or captured_by.value, "audio_id": audio_id,
                                     "stt": stt_info},
                           "rules": {"ms": 0, "facts": [], "rejected": []},
                           "model": model,
                           "guard": {"instruction_shaped": injected,
                                     **({"policy": "every fact from this utterance needs the medic's tap"}
                                        if injected and not skip else {})},
                           "effects": {"readiness": [], "alerts_new": [], "scores": [], "gaps_closed": []}}}
        self.inc.transcripts.append(entry)
        if model["status"] == "running":
            self.ctx.speech_in_flight += 1
            asyncio.create_task(self._extract_counted(entry, text, captured_by, default_role, speaker, audio_id, injected))
        await self._saved_broadcast()
        if model["status"] == "unavailable":
            raise ModelUnavailable(model["reason"])
        return {"transcript": entry, "facts": []}

    async def _extract_counted(self, *args):
        try:
            await self._extract(*args)
        finally:
            self.ctx.speech_in_flight -= 1

    async def retry_text(self, entry_id: str) -> dict:
        """Retry preserved words after a temporary local-model outage without duplicating evidence."""
        self.inc.ensure_open()
        entry = next((row for row in self.inc.transcripts if row["id"] == entry_id), None)
        if entry is None:
            raise KeyError(entry_id)
        if entry["trace"]["model"]["status"] != "unavailable":
            raise ValueError("only words kept while the extraction model was unavailable can be retried")
        if not self.ctx.text_model.available():
            raise ModelUnavailable("the extraction model is still not running")
        captured_by = CapturedBy(entry["captured_by"])
        speaker, text = entry.get("speaker"), entry["text"]
        default_role = source_role(captured_by, speaker)
        entry["trace"]["model"] = {"status": "running", "name": self.ctx.text_model.model_name(), "retry": True}
        self.ctx.speech_in_flight += 1
        await self._saved_broadcast()
        asyncio.create_task(self._extract_counted(entry, text, captured_by, default_role, speaker, entry.get("audio_id"), None))
        return entry

    async def stt_failure(self, audio_id: str, captured_by: CapturedBy, speaker: Optional[str], error: str,
                          ms: int) -> dict:
        self.inc.ensure_open()
        before = self._summary()
        stt = {"seconds": None, "chunks": [], "ms": ms, "error": error[:200]}
        entry = {"id": new_id("t"), "ts": utcnow().isoformat(), "text": "[speech-to-text failed]",
                 "captured_by": captured_by.value, "speaker": speaker, "audio_id": audio_id, "fact_ids": [],
                 "extract": {"rules": 0, "llm": None, "ms": 0}, "stt": stt,
                 "trace": {"heard": {"text": "", "speaker": speaker or captured_by.value, "audio_id": audio_id,
                                      "stt": stt}, "rules": {"ms": 0, "facts": [], "rejected": []},
                           "model": {"status": "error", "error": f"speech-to-text failed: {error[:160]}"},
                           "guard": {"instruction_shaped": None}, "effects": self.ctx.tracer.diff(before, before)}}
        self.inc.transcripts.append(entry)
        await self._saved_broadcast()
        return entry

    @staticmethod
    def _hold(facts: list, phrase: str) -> None:
        """Instruction-shaped speech: nothing from the utterance may confirm itself, and the screen says why."""
        reason = f'said together with a command to the system ("{phrase}"): check before confirming'
        for f in facts:
            f.confidence = min(f.confidence, 0.5)
            f.provenance.hold_reason = join_reasons(reason, f.provenance.hold_reason)   # keep a drug-match reason

    async def _extract(self, entry: dict, text: str, captured_by: CapturedBy, default_role: Role,
                       speaker: Optional[str], audio_id: Optional[str], hold: Optional[str]) -> None:
        ctx, tracer = self.ctx, self.ctx.tracer
        before = self._summary()
        t0 = time.perf_counter()
        name = ctx.text_model.model_name()
        try:
            facts_in = await run_in_threadpool(partial(ctx.model_extractor.extract, dispatch=self.inc.dispatch),
                                               text, captured_by, default_role, speaker, audio_id)
            if hold:
                self._hold(facts_in, hold)
            usage = ctx.model_extractor.last_usage or {}
            rejected: list = []
            added = self.ingest_batch(facts_in, rejected)
            entry["fact_ids"] += [f.id for f in added]
            entry["extract"]["llm"] = len(added)
            entry["trace"]["model"] = {"status": "done", "name": name, "ms": round((time.perf_counter() - t0) * 1000),
                                       "tokens": usage.get("completion_tokens"), "proposed": len(facts_in),
                                       "facts": [tracer.fact_view(f) for f in added], "rejected": rejected,
                                       "auto_confirm_threshold": ctx.policy.auto_confirm}
            entry["trace"]["effects"] = tracer.diff(before, self._summary())
        except Exception as e:
            entry["trace"]["model"] = {"status": "error", "name": name, "error": str(e)[:200],
                                       "ms": round((time.perf_counter() - t0) * 1000)}
        await self._saved_broadcast()

    # ---------- photo ----------
    async def photo(self, raw: bytes, mode: str, *, auto=False, frame=None, intent=None, roi=None, valid=None):
        if auto:
            return await self.ctx.frame_reader.read(frame, intent, roi, valid)
        ctx, tracer = self.ctx, self.ctx.tracer
        photo_id = new_id("p")
        with self.inc.lock:
            self.inc.ensure_open()
            ctx.settings.photo_dir.mkdir(parents=True, exist_ok=True)
            (ctx.settings.photo_dir / f"{photo_id}.jpg").write_bytes(raw)
            self.inc.register_media("photo", photo_id)
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
                              "model": {"status": "error", "name": ctx.vision_model.model_name(), "error": str(e)[:200],
                                        "ms": round((time.perf_counter() - t0) * 1000)},
                              "effects": tracer.diff(before, before)}
            self.inc.transcripts.append(entry)
            await self._saved_broadcast()
            raise
        ms = round((time.perf_counter() - t0) * 1000)
        rejected: list = []
        facts = self.ingest_batch(facts_in, rejected)
        entry["fact_ids"] = [f.id for f in facts]
        entry["extract"] = {"rules": 0, "llm": len(facts), "ms": ms}
        entry["trace"] = {"heard": heard, "rules": {"ms": 0, "facts": []},
                          "model": {"status": "done", "name": ctx.vision_model.model_name(), "ms": ms,
                                    "facts": [tracer.fact_view(f) for f in facts], "rejected": rejected},
                          "effects": tracer.diff(before, self._summary())}
        self.inc.transcripts.append(entry)
        await self._saved_broadcast()
        return {"photo_id": photo_id, "facts": [f.model_dump(mode="json") for f in facts]}

    # ---------- structured readings (monitor panel, device feed) ----------
    async def correct(self, fact_id: str, value) -> dict:
        inc, tracer = self.inc, self.ctx.tracer
        before = tracer.summarize(inc.snapshot())
        corrected = inc.correct(fact_id, value)
        said = f"Corrected {self.ctx.vocab.label(corrected.key)} from {corrected.previous_value} to {corrected.value}"
        inc.transcripts.append({
            "id": new_id("t"), "ts": utcnow().isoformat(), "text": said, "captured_by": "medic",
            "speaker": "medic correction", "audio_id": None, "fact_ids": [corrected.id],
            "extract": {"rules": 0, "llm": None, "ms": 0},
            "trace": {"heard": {"text": said, "speaker": "medic correction", "source": "structured"},
                      "rules": {"ms": 0, "facts": [tracer.fact_view(corrected)]},
                      "model": {"status": "off", "reason": "explicit medic correction; nothing to extract"},
                      "guard": {"instruction_shaped": None},
                      "effects": tracer.diff(before, tracer.summarize(inc.snapshot()))}})
        await self._saved_broadcast()
        return corrected.model_dump(mode="json")

    async def structured(self, facts: list[FactIn]) -> list[dict]:
        """All-or-nothing: one invalid fact rejects the batch (ValueError). One trace entry per call. Drug names are
        coded here like the extractors' (a device or form may send them)."""
        self.inc.ensure_open()
        facts = [FactIn(key=f.key, value=f.value, unit=f.unit, role=Role.device,
                        speaker="monitor", captured_by=CapturedBy.device, confidence=0.0,
                        provenance=Provenance(extractor="manual", hold_reason="device reading: confirm before relay"))
                 for f in facts]
        tracer = self.ctx.tracer
        if self.ctx.coder:
            facts = self.ctx.coder.code(facts)
        for f in facts:
            self.inc.validate(f)
        before = self._summary()
        added = [self.inc.ingest(f, record=False) for f in facts]
        self.inc.commit()
        self.notify(added, before)
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
        await self._saved_broadcast()
        return [f.model_dump(mode="json") for f in added]
