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

from ..capture.types import IncidentEvent
from ..core.incident import IncidentEnded
from ..core.schema import CapturedBy, FactIn, Provenance, Role, join_reasons, new_id, source_role, utcnow
from .context import AppContext

Broadcast = Callable[[], Awaitable[None]]

# The speaker of ambient cabin speech is never inferred. The screen shows this label on the fact as it is and leaves
# it out of the activity line (ui/src/lib/format.ts UNIDENTIFIED_SPEAKER, the same string).
AMBIENT_SPEAKER = "Speaker not identified"


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

    async def _saved_broadcast(self) -> None:
        self.ctx.persist()
        await self.broadcast()

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
                f.speaker = AMBIENT_SPEAKER
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
        self.inc.ensure_open()
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
        asked = ctx.cues.ask(self.inc.id, text) if ctx.cues is not None else None   # "show me the protocol for ..."
        entry["asked"] = bool(asked)
        if model["status"] == "running":
            self.ctx.speech_in_flight += 1
            asyncio.create_task(self._extract_counted(entry, text, captured_by, default_role, speaker, audio_id, injected))
        await self._saved_broadcast()
        if model["status"] == "unavailable":
            raise ModelUnavailable(model["reason"])
        return {"transcript": entry, "facts": []}

    def _forget(self, entry: dict) -> None:
        """Drop overheard words that held nothing about the patient: the entry leaves the call's record and its audio
        is deleted now, not at the end of the call. Only the count remains (telemetry)."""
        with self.inc.lock:
            if entry in self.inc.transcripts:
                self.inc.transcripts.remove(entry)
            audio_id = entry.get("audio_id")
            if audio_id:
                self.inc.media_ids["audio"].discard(audio_id)
                (self.ctx.settings.audio_dir / f"{audio_id}.wav").unlink(missing_ok=True)
        self.ctx.telemetry.record_stt_dropped("nothing clinical")      # counted beside the speech gates' drops

    async def _extract_counted(self, *args):
        try:
            await self._extract(*args)
        finally:
            self.ctx.speech_in_flight -= 1

    async def retry_text(self, entry_id: str) -> dict:
        """Retry words preserved while the extraction model was unavailable, without creating a duplicate entry."""
        self.inc.ensure_open()
        entry = next((entry for entry in self.inc.transcripts if entry["id"] == entry_id), None)
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
        await self._saved_broadcast()
        self.ctx.speech_in_flight += 1
        asyncio.create_task(self._extract_counted(entry, text, captured_by, default_role, speaker,
                                                  entry.get("audio_id"), None))
        return entry

    async def stt_failure(self, audio_id: str, captured_by: CapturedBy, speaker: Optional[str], error: str,
                          ms: int) -> dict:
        """Keep an evidence-backed trace when speech-to-text fails before words are available."""
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
        overheard = captured_by == CapturedBy.other and default_role == Role.unknown   # the room microphone
        try:
            facts_in = await run_in_threadpool(partial(ctx.model_extractor.extract, dispatch=self.inc.dispatch),
                                               text, captured_by, default_role, speaker, audio_id)
            discarded: list = []
            # Every utterance, the medic's own included: from "history of diabetes, hypertension" the extractor
            # listed metformin, insulin and lisinopril as the patient's medications (8103 test, 2026-09-26).
            if facts_in and ctx.fact_verifier is not None:
                try:                        # a second read: do these words say this about the patient?
                    facts_in, discarded = await run_in_threadpool(ctx.fact_verifier.check, text, facts_in, self.inc.dispatch)
                except Exception as e:      # not checked: every proposal stays, unconfirmed, and the trace says why
                    discarded = [{"error": f"not checked: {str(e)[:120]}"}]
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
                                       "discarded": discarded,
                                       "auto_confirm_threshold": ctx.policy.auto_confirm}
            entry["trace"]["effects"] = tracer.diff(before, self._summary())
            if overheard and not added and not entry.get("asked"):
                self._forget(entry)         # overheard words with nothing clinical in them are not part of the record
        except IncidentEnded:
            # The call changed while local extraction was running. Discard the late result;
            # it must not mutate the ended patient or be persisted into the new call.
            return
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
        except IncidentEnded:
            raise
        except Exception as e:
            # The photo is kept and the failure recorded, so the medic's screen shows it.
            entry["trace"] = {"heard": heard, "rules": {"ms": 0, "facts": []},
                              "model": {"status": "error", "name": ctx.vision_model.model_name(), "error": str(e)[:200],
                                        "ms": round((time.perf_counter() - t0) * 1000)},
                              "effects": tracer.diff(before, before)}
            with self.inc.lock:
                self.inc.ensure_open()
                self.inc.transcripts.append(entry)
            await self._saved_broadcast()
            raise
        ms = round((time.perf_counter() - t0) * 1000)
        with self.inc.lock:
            self.inc.ensure_open()
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
        await self.broadcast()
        return corrected.model_dump(mode="json")

    async def structured(self, facts: list[FactIn]) -> list[dict]:
        """All-or-nothing: one invalid fact rejects the batch (ValueError). One trace entry per call. Drug names are
        coded here like the extractors' (a device or form may send them)."""
        self.inc.ensure_open()
        # This HTTP endpoint is a device feed, not an authenticated medic-entry endpoint.
        # Never let a client turn an arbitrary submitted value into a confirmed medic fact.
        # A device value is useful to show immediately, but requires an explicit medic tap
        # before it may affect scores, alerts, or the relay.
        facts = [FactIn(key=f.key, value=f.value, unit=f.unit, role=Role.device,
                        speaker="monitor", captured_by=CapturedBy.device, confidence=0.0,
                        provenance=Provenance(extractor="manual",
                                              hold_reason="device reading: confirm before relay"))
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
