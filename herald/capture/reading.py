"""Selected still -> proposed facts or dose evidence. No capture policy or HTTP here."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi.concurrency import run_in_threadpool

from ..core.schema import CapturedBy, Role, Status, Verification, new_id, utcnow
from ..core.vocabulary import norm_value
from .frames import cropped
from .types import CaptureResult


class FrameReader:
    def __init__(self, config, incident, vision, store, drug_check, tracer, model_name, broadcast):
        self.config, self.incident, self.vision = config, incident, vision
        self.store, self.drug_check, self.tracer = store, drug_check, tracer
        self.model_name, self.broadcast = model_name, broadcast

    def _keep(self, inc, frame):
        """Store a used still and attach it to the call, so ending the call deletes it (herald/api/media.py)."""
        photo_id = self.store.store(frame, used=True)
        if photo_id is not None:
            try:
                inc.register_media("evidence", photo_id)
            except Exception:
                (self.store.directory / f"{photo_id}.jpg").unlink(missing_ok=True)   # call ended: keep nothing
                raise
        return photo_id

    async def read(self, frame, intent, roi, valid):
        inc = self.incident()
        before = self.tracer.summarize(inc.snapshot())
        raw = cropped(frame, roi if intent.mode == "monitor" else None, self.config["monitor"]["roi_margin"])
        start = time.perf_counter()
        facts = await run_in_threadpool(self.vision.read, raw, intent.mode, frame.id)
        if not valid() or inc is not self.incident():
            return CaptureResult(reason="cancelled or patient changed")
        photo_id, added, reason = None, [], intent.reason
        if intent.purpose == "verify":
            dose = next((f for f in inc.facts if f.id == intent.fact_id and f.status != Status.rejected), None)
            result = self.drug_check.compare(dose, facts) if dose else None
            if result and result.status != "unreadable":
                photo_id = self._keep(inc, frame)
                c = self.config["verify"]
                reason = c["mismatch"].format(said=dose.value[c["drug_field"]], label=result.label_drug) if result.status == "mismatch" else "Ingredient label matches; dose and administration not verified"
                inc.apply_verification(dose.id, Verification(status=result.status, label_drug=result.label_drug,
                                                            photo_id=photo_id), pending_reason=c["pending"],
                                       reason=reason if result.status == "mismatch" else None)
                added = [dose]
            else:
                reason = "Label unreadable or ambiguous; spoken dose unchanged"
        else:
            allowed = self.config["record_keys"][intent.mode]
            proposed = []
            for source in facts:
                if not any(source.key.startswith(k) if k.endswith(".") else source.key == k for k in allowed):
                    continue
                f = source.model_copy(deep=True)
                f.captured_by, f.role = CapturedBy.camera, Role.photo
                f.provenance.photo_id = None
                f.provenance.trigger, f.provenance.frame_id, f.provenance.auto = intent.trigger, frame.id, intent.trigger != "manual"
                f.provenance.observed_at = datetime.fromtimestamp(frame.ts, timezone.utc)
                f.provenance.crop = list(roi.__dict__.values()) if roi and intent.mode == "monitor" else None
                f.provenance.text = f"{intent.reason}; frame {frame.id} at {frame.ts}"
                try:
                    inc.validate(f)
                except ValueError:
                    continue
                proposed.append(f)
            latest = [inc.latest(f.key) for f in proposed]
            unchanged = bool(proposed) and all(old is not None and norm_value(old.value) == norm_value(f.value)
                         and time.time() - old.ts.timestamp() < self.config["monitor"]["max_interval_s"]
                         for f, old in zip(proposed, latest))
            if intent.mode == "monitor" and unchanged:
                proposed = []; reason = "unchanged"
            if proposed:
                photo_id = self._keep(inc, frame)
                for f in proposed:
                    f.provenance.photo_id = photo_id
                    added.append(inc.ingest(f, record=False))
                inc.commit()
            elif reason != "unchanged":
                reason = "No usable facts in selected frame"
        ms = round((time.perf_counter() - start) * 1000)
        trace = {"heard": {"text": reason, "photo_id": photo_id, "frame_id": frame.id},
                 "rules": {"ms": 0, "facts": []},
                 "model": {"status": "done", "name": self.model_name(), "ms": ms,
                           "facts": [self.tracer.fact_view(f) for f in added]},
                 "effects": self.tracer.diff(before, self.tracer.summarize(inc.snapshot()))}
        # The call's record keeps what the camera contributed, not every frame it looked at: a frame that gave nothing
        # new (unusable, or the same reading) is counted in the capture status (`capture.last`, `counts`) and no more.
        if added:
            inc.transcripts.append({"id": new_id("t"), "ts": utcnow().isoformat(), "text": reason, "captured_by": "camera",
                                    "speaker": intent.mode, "audio_id": None, "photo_id": photo_id,
                                    "trigger": intent.trigger, "reason": reason, "frame_id": frame.id,
                                    "fact_ids": [f.id for f in added], "extract": {"rules": 0, "llm": len(added), "ms": ms}, "trace": trace})
        await self.broadcast()
        return CaptureResult([f.id for f in added], photo_id, reason)
