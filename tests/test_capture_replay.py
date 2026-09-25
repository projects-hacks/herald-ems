"""CPU-only rehearsal: real frame source, policy, HTTP surface and coder; fake readers only."""
import asyncio
from dataclasses import replace
from pathlib import Path

from fakes import FakeModel, FakeVision, make_client, tiny_normalizer
from herald.capture.config import capture_config
from herald.capture.sources import BrowserFrameSource, ReplayFrameSource
from herald.core.schema import FactIn

FOLDER = Path(__file__).resolve().parents[1] / "scenarios/frames/auto_capture"


class FrameVision(FakeVision):
    def __init__(self):
        self.rows, self.calls = {}, []

    def read(self, raw, mode, photo_id=None):
        self.calls.append((photo_id, mode))
        return self.rows.get(photo_id, [])


def test_replay_source_restarts_and_browser_queue_is_bounded():
    source = ReplayFrameSource(FOLDER, 1, capture_config(), clock=lambda: 100)
    first = next(source.frames())
    source.close()
    assert next(source.frames()).jpeg == first.jpeg
    browser = BrowserFrameSource(max_frames=1)
    browser.push(first); browser.push(replace(first, id="new"))
    assert [f.id for f in browser.frames()] == ["new"]
    browser.close()
    assert list(browser.frames()) == []


def test_synthetic_rehearsal_through_capture_api(tmp_path):
    vision = FrameVision()
    client, ctx = make_client(vision=vision, normalizer=tiny_normalizer(), data_dir=tmp_path,
                              capture_source="browser")
    frames = list(ReplayFrameSource(FOLDER, 1, capture_config(), clock=lambda: 100).frames())
    vision.rows = {frames[0].id: [FactIn(key="vitals.hr", value=95)],
                   frames[1].id: [FactIn(key="vitals.hr", value=110)],
                   frames[2].id: [FactIn(key="meds.list", value=["ondansetron"])],
                   frames[3].id: [FactIn(key="code_status", value="DNR")]}
    now = [100.0]
    agent = ctx.capture_agent
    agent.clock = lambda: now[0]
    ctx.frame_reader.store.blur = lambda raw: raw  # synthetic props only; redaction separately tested

    def feed(index, stable=False):
        async def run():
            agent.receive(replace(frames[index], ts=now[0]))
            if stable:
                now[0] += 1
                agent.receive(replace(frames[index], ts=now[0]))
            await agent.step()
            if agent.read_task: await agent.read_task
        asyncio.run(run())

    client.post("/api/capture/auto", json={"on": True})
    client.post("/api/capture/roi", json={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    feed(0, stable=True)
    assert client.get("/api/state").json()["facts"]["vitals.hr"]["value"] == 95
    now[0] += capture_config()["monitor"]["min_interval_s"] + 1; feed(1, stable=True)  # past the configured spacing
    assert client.get("/api/state").json()["facts"]["vitals.hr"]["value"] == 110
    assert all(f.status.value == "unconfirmed" for f in ctx.incident.facts)
    client.delete("/api/capture/roi")
    now[0] += 11
    client.post("/api/facts", json=[{"key": "meds.given", "value": {"drug": "Narcan", "dose": .4, "unit": "mg", "by": "crew"}}])
    feed(2)
    state = client.get("/api/state").json()
    assert state["facts"]["meds.given"]["verify"]["status"] == "mismatch"
    assert "meds.list" not in state["facts"]
    client.post("/api/capture/auto", json={"on": False})
    now[0] += 1
    client.post("/api/capture/now", json={"mode": "form"})
    feed(3)
    assert client.get("/api/state").json()["facts"]["code_status"]["status"] == "unconfirmed"
    assert len(vision.calls) == 4
    assert len(list(tmp_path.rglob("auto_*.jpg"))) == 4


def test_fake_speech_extraction_emits_verify_intent_without_phrase_matching(tmp_path):
    model = FakeModel(rows=[["meds.given", {"drug": "Narcan", "dose": .4, "unit": "mg", "by": "crew"}, "m"]])
    client, ctx = make_client(model=model, normalizer=tiny_normalizer(), data_dir=tmp_path)
    client.post("/api/capture/auto", json={"on": True})
    async def run():
        from herald.core.schema import CapturedBy
        entry = await client.app.state.capture.for_incident().text(
            "We are drawing up 0.4 milligrams of Narcan, given by our crew.", CapturedBy.medic, None, None, None)
        for _ in range(100):
            if entry["transcript"]["trace"]["model"]["status"] != "running": break
            await asyncio.sleep(.01)
        assert ctx.speech_in_flight == 0
        assert any(intent.purpose == "verify" for intent, _, _ in ctx.capture_agent.pending)
    asyncio.run(run())
