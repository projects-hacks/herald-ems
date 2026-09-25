"""CPU orchestration: bounded frames/intents, policy, admission, and an injected still reader."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import asdict
from typing import Awaitable, Callable

import numpy as np

from .buffer import FrameBuffer
from .gate import FrameGate
from .policy import CapturePolicy
from .scheduler import CaptureScheduler
from .types import CaptureIntent, CaptureResult, Frame, IncidentEvent, ROI


class CaptureAgent:
    def __init__(self, config: dict, reader: Callable[..., Awaitable[CaptureResult]], *,
                 incident_id: Callable[[], str], speech_busy: Callable[[], bool], source="off", clock=time.time,
                 notify=None, hold=None):
        self.config, self.reader, self.incident_id, self.speech_busy = config, reader, incident_id, speech_busy
        self.source, self.clock = source, clock
        self.auto, self.roi = False, None
        self.gate, self.monitor_gate = FrameGate(config["gate"]), FrameGate(config["gate"])
        self.buffer = FrameBuffer(config["buffer_s"], config["max_frames"])
        self.monitor_buffer = FrameBuffer(config["buffer_s"], config["max_frames"])
        self.policy, self.scheduler = CapturePolicy(config), CaptureScheduler(config["rate"])
        self.last_decisions = deque(maxlen=config["decision_history"])
        self.pending = deque(maxlen=config["queue_size"])
        self.counts = dict(frames=0, gated=0, captured=0, stored=0)
        self.generation = 0
        self.owner = incident_id()
        self.last_input = float("-inf")
        self.task = self.read_task = None
        self.frame_source = None
        self.last_error = None
        self.notify, self.hold = notify, hold

    def status(self):
        fresh = self.clock() - self.last_input <= self.config["buffer_s"]
        return {"auto": self.auto, "source": self.source, "fps_in": self.config["fps_in"], "incident_id": self.owner,
                "roi": asdict(self.roi) if self.roi else None,
                "sees": "reading" if self.scheduler.in_flight else "watching" if self.auto and fresh else "off",
                "last": self.last_decisions[-1] if self.last_decisions else None, "counts": dict(self.counts),
                "error": self.last_error, "pending": len(self.pending)}

    def reset(self):
        self.generation += 1
        self.buffer.clear(); self.monitor_buffer.clear()
        self.gate.clear(); self.monitor_gate.clear()
        self.pending.clear(); self.policy.stable = 0
        self.last_input = float("-inf")

    def patient_changed(self):
        if self.owner != self.incident_id():
            self.auto = False; self.roi = None; self.reset()
            self.policy.reset()
            self.owner = self.incident_id(); self.last_decisions.clear()
            self.counts = dict(frames=0, gated=0, captured=0, stored=0)

    def set_auto(self, on: bool):
        self.patient_changed()
        self.reset()
        self.auto = on
        if not on and self.frame_source:
            self.frame_source.close()

    def set_roi(self, roi: ROI | None):
        self.patient_changed(); self.reset(); self.roi = roi

    def enqueue(self, intent: CaptureIntent, *, manual=False):
        key = (intent.trigger, intent.fact_id)
        if any((i.trigger, i.fact_id) == key for i, _, _ in self.pending):
            return
        if len(self.pending) >= self.pending.maxlen:
            self.last_error = "Capture queue full; request not queued"
            return
        expiry = self.clock() + (self.config["manual_wait_s"] if manual else intent.window_s)
        insert = self.pending.appendleft if manual or intent.purpose == "verify" else self.pending.append
        insert((intent, expiry, manual))

    def on_change(self, event: IncidentEvent):
        self.patient_changed()
        if not self.auto or (event.incident_id and event.incident_id != self.owner):
            return
        # Camera facts cannot trigger a self-sustaining capture loop.
        facts = [f for f in event.facts if f.captured_by.value != "camera"]
        if event.kind == "facts_added" and not facts:
            return
        event = IncidentEvent(event.kind, facts, event.summary_diff, event.incident_id, event.states)
        for intent in self.policy.on_event(event):
            if intent.purpose == "verify" and self.hold:
                self.hold(intent.fact_id, self.config["verify"]["pending"])
            self.enqueue(intent)

    def manual(self, mode: str | None = None):
        self.patient_changed()
        mode = mode or ("monitor" if self.roi else "pill_bottle")
        self.enqueue(CaptureIntent("manual", mode, self.config["manual_window_s"], "monitor" if mode == "monitor" else None,
                                   reason="Show Herald"), manual=True)

    def receive(self, frame: Frame):
        self.patient_changed()
        now = self.clock()
        if frame.ts > now or frame.ts < now - self.config["buffer_s"]:
            return None
        if not self.auto and not any(manual for _, _, manual in self.pending):
            return None
        if now - self.last_input < 1 / self.config["fps_in"]:
            return None
        self.last_input = now
        self.counts["frames"] += 1
        result = self.gate.assess(frame)
        self.buffer.add(frame, result)
        self.counts["gated"] += int(result.passed)
        if self.roi and self.auto:
            previous = self.monitor_gate.current
            monitor = self.monitor_gate.assess(frame, self.roi)
            current = self.monitor_gate.current
            stable = previous is not None and previous.shape == current.shape and float(np.abs(previous - current).mean() / 255) < self.config["gate"]["change_min"]
            self.monitor_buffer.add(frame, monitor)
            for intent in self.policy.on_tick(now, {"roi": True, "usable": monitor.usable, "stable": stable, "changed": monitor.passed}):
                self.enqueue(intent)
            result = monitor
        return result

    async def step(self):
        self.patient_changed()
        now = self.clock()
        self.buffer.prune(now); self.monitor_buffer.prune(now)
        while self.pending and self.pending[0][1] < now:
            intent, _, _ = self.pending.popleft()
            self.last_decisions.append({"ts": now, "trigger": intent.trigger, "mode": intent.mode,
                                        "reason": "no usable frame before request expired", "facts": [], "photo_id": None})
        if not self.pending or self.scheduler.in_flight:
            return
        intent, expiry, manual = self.pending[0]
        buffer = self.monitor_buffer if intent.mode == "monitor" and self.roi and not manual else self.buffer
        frame = buffer.best(now - intent.window_s, now, manual=manual, refresh=intent.trigger == "monitor_refresh")
        if frame is None or not self.scheduler.acquire(now, manual=manual, speech_busy=self.speech_busy()):
            return
        self.pending.popleft()
        token, owner, roi = self.generation, self.owner, self.roi
        valid = lambda: token == self.generation and owner == self.incident_id()
        self.counts["captured"] += 1
        self.read_task = asyncio.create_task(self._read(frame, intent, roi, valid))
        if self.notify:
            await self.notify()

    async def _read(self, frame, intent, roi, valid):
        try:
            result = await self.reader(frame, intent, roi, valid)
            if not valid():
                return
            self.gate.accept(frame)
            if intent.mode == "monitor" and roi:
                self.monitor_gate.accept(frame, roi)
            self.policy.captured(intent, self.clock())
            self.counts["stored"] += int(result.photo_id is not None)
            self.last_decisions.append({"ts": self.clock(), "trigger": intent.trigger, "mode": intent.mode,
                                        "reason": result.reason, "facts": result.facts, "photo_id": result.photo_id})
            self.last_error = None
        except Exception as e:
            if valid():
                self.last_error = f"Capture failed: {str(e)[:160]}"
        finally:
            self.scheduler.release()
            if self.notify:
                await self.notify()

    def start(self, frame_source=None):
        if self.task and not self.task.done():
            return
        self.frame_source = frame_source
        self.task = asyncio.create_task(self._run())

    async def _run(self):
        iterator, generation = None, -1
        next_frame = 0
        try:
            while True:
                now = self.clock()
                if self.frame_source and generation != self.generation:
                    iterator = iter(self.frame_source.frames())
                    generation = self.generation
                    next_frame = now
                if iterator and now >= next_frame and (self.auto or self.pending):
                    frame = next(iterator, None)
                    if frame:
                        self.receive(frame)
                    next_frame = now + 1 / self.config["fps_in"]
                await self.step()
                await asyncio.sleep(self.config["poll_s"])
        except asyncio.CancelledError:
            pass

    async def stop(self):
        self.set_auto(False)
        if self.task:
            self.task.cancel()
            await self.task
        if self.read_task:
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass
