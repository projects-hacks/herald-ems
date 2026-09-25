import asyncio

from herald.capture.agent import CaptureAgent
from herald.capture.config import capture_config
from herald.capture.types import CaptureResult, ROI
from herald.capture.types import IncidentEvent
from test_capture_gate import frame


def test_monitor_manual_off_and_speech_priority():
    async def run():
        now, busy, calls = [0.0], [False], []
        async def read(f, intent, roi, valid):
            calls.append(intent.trigger)
            return CaptureResult(["fact"])
        agent = CaptureAgent(capture_config(), read, incident_id=lambda: "one", speech_busy=lambda: busy[0],
                             source="browser", clock=lambda: now[0])
        assert agent.receive(frame()) is None
        agent.set_auto(True); agent.set_roi(ROI(0, 0, 1, 1))
        agent.receive(frame())
        now[0] = 1; agent.receive(frame(1)); busy[0] = True
        await agent.step(); assert calls == []
        busy[0] = False; await agent.step(); await agent.read_task
        assert calls == ["monitor_changed"]
        now[0] = 2; agent.receive(frame(2)); await agent.step()
        assert calls == ["monitor_changed"]
        agent.set_auto(False)
        assert not agent.buffer.items and not agent.pending
        agent.manual("form"); agent.receive(frame(2, blur=True))
        await agent.step(); await agent.read_task
        assert calls == ["monitor_changed", "manual"]
        await agent.stop()
    asyncio.run(run())


def test_patient_change_invalidates_inflight_result_and_clears_roi():
    async def run():
        owner = ["one"]; released = asyncio.Event(); writes = []
        async def read(f, intent, roi, valid):
            await released.wait()
            if valid(): writes.append("stored")
            return CaptureResult(["fact"])
        agent = CaptureAgent(capture_config(), read, incident_id=lambda: owner[0], speech_busy=lambda: False,
                             source="browser", clock=lambda: 0)
        agent.set_auto(True); agent.set_roi(ROI(0, 0, 1, 1)); agent.manual(); agent.receive(frame())
        await agent.step(); await asyncio.sleep(0)
        owner[0] = "two"; agent.patient_changed(); released.set(); await agent.read_task
        assert not writes and not agent.last_decisions and agent.roi is None and not agent.auto
        await agent.stop()
    asyncio.run(run())


def test_eta_is_once_per_patient_not_once_per_toggle_or_region():
    owner = ["one"]
    agent = CaptureAgent(capture_config(), None, incident_id=lambda: owner[0], speech_busy=lambda: False)
    event = IncidentEvent("eta_changed", [], {"eta_min": 5})
    agent.set_auto(True); agent.on_change(event)
    assert len(agent.pending) == 1
    agent.set_auto(False); agent.set_auto(True); agent.set_roi(ROI(0, 0, 1, 1)); agent.on_change(event)
    assert not agent.pending
    owner[0] = "two"; agent.set_auto(True); agent.on_change(event)
    assert len(agent.pending) == 1
