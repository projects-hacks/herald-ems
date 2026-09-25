#!/usr/bin/env python3
"""Replay a scenario against a running Herald server (rehearsal, video, regression).

  python scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8100 [--fast] [--no-llm]
  (--no-llm: words only, nothing extracted; there is no rules extractor in the product)
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from herald.config import get_settings

ap = argparse.ArgumentParser()
ap.add_argument("scenario")
ap.add_argument("--url", default="http://localhost:8100")
ap.add_argument("--fast", action="store_true", help="no pauses")
ap.add_argument("--no-llm", action="store_true", help="send the words without extraction (model status off)")
ap.add_argument("--lkw-minutes-ago", type=int, default=64)
a = ap.parse_args()

sc = json.load(open(a.scenario))
lkw = (datetime.now(ZoneInfo(get_settings().timezone)) - timedelta(minutes=a.lkw_minutes_ago)).strftime("%-I:%M")
c = httpx.Client(base_url=a.url, timeout=120)


def wait_model(entry_id: str, timeout: float = 30.0) -> dict:
    """The transcript entry once its model phase is no longer running."""
    t0 = time.perf_counter()
    while True:
        e = next(t for t in c.get("/api/state").json()["transcripts"] if t["id"] == entry_id)
        if e["trace"]["model"]["status"] != "running" or time.perf_counter() - t0 > timeout:
            return e
        time.sleep(0.1)


for step in sc["steps"]:
    if "incident" in step:
        c.post("/api/incident", json={"dispatch": step["incident"]}).raise_for_status()
        print(f"[incident] {step['incident']}")
    elif "patient" in step:
        roster = c.get("/api/patients").raise_for_status().json()["patients"]
        match = next((row for row in roster if row["label"] == step["patient"]), None)
        if match:
            state = c.post(f"/api/patients/{match['id']}/activate").raise_for_status().json()
            action = "activated"
        else:
            state = c.post("/api/patients", json={"label": step["patient"]}).raise_for_status().json()
            action = "created"
        print(f"[patient] {action} {step['patient']} ({state['active_patient']})")
    elif "link" in step:
        mode = step["link"]
        c.post(f"/api/netem/{mode}").raise_for_status()
        print(f"[link] {mode}")
    elif "authorize" in step:
        destination = step["authorize"]
        c.post("/api/relay/authorize", json={"destination": destination,
                                             "scope": step.get("scope", "mass-casualty pre-alert set")}).raise_for_status()
        print(f"[relay] authorized {destination}")
    elif "say" in step:
        text = step["say"].replace("LKW_TIME", lkw)
        body = {"text": text, "captured_by": step.get("by", "medic"), "speaker": step.get("speaker"),
                "use_llm": not a.no_llm}
        t0 = time.perf_counter()
        r = c.post("/api/transcript", json=body)
        r.raise_for_status()
        e = wait_model(r.json()["transcript"]["id"])            # words first; the model's facts follow on the entry
        m = e["trace"]["model"]
        print(f"[{step.get('speaker') or step.get('by', 'medic')}] {text}\n    -> model {m['status']}, "
              f"{len(m.get('facts', []))} facts in {time.perf_counter() - t0:.2f}s")
        for f in m.get("facts", []):
            held = f"  held: {f['hold_reason']}" if f.get("hold_reason") else ""
            print(f"       {f['key']} = {json.dumps(f['value'])} ({f['role']}, {f['status']}, "
                  f"confidence {f.get('confidence')}){held}")
    elif "confirm" in step:
        # The medic's taps: wait for model phases to finish, then confirm this key group's unconfirmed facts.
        for _ in range(120):
            if all(t["trace"]["model"]["status"] != "running" for t in c.get("/api/state").json()["transcripts"]):
                break
            time.sleep(0.25)
        state = c.get("/api/state").json()
        # every held fact of the key group: the latest per key, and every event (each dose given, each procedure)
        held = {f["id"]: f for f in [*state["facts"].values(), *[e for ev in (state.get("events") or {}).values() for e in ev]]
                if f["key"].startswith(step["confirm"]) and f["status"] == "unconfirmed"}
        done = [f["key"] for f in held.values() if not c.post(f"/api/facts/{f['id']}/confirm").raise_for_status() is None]
        print(f"[tap] confirmed {done}")
    elif "photo" in step:
        # A photo from the phone camera (stage: a real watch or bottle; replay: a test image)
        with open(step["photo"], "rb") as fh:
            r = c.post("/api/photo", files={"file": ("photo.jpg", fh, "image/jpeg")}, data={"mode": step.get("mode", "monitor")})
        r.raise_for_status()
        facts = r.json()["facts"]
        print(f"[photo:{step.get('mode', 'monitor')}] {step['photo']}\n    -> {len(facts)} facts")
        for f in facts:
            print(f"       {f['key']} = {json.dumps(f['value'])} ({f['status']}, confidence {f['confidence']})")
    elif "ask" in step:
        # A protocol question: the county's own passage, with its citation
        r = c.get("/api/protocols/search", params={"q": step["ask"]})
        deadline = time.monotonic() + 600
        while r.status_code == 503 and (r.json().get("detail") or {}).get("building") and time.monotonic() < deadline:
            time.sleep(5)                                    # a fresh server is still building the county index
            r = c.get("/api/protocols/search", params={"q": step["ask"]})
        if r.status_code == 404:
            print(f"[ask] {step['ask']}\n    -> protocol lookup is off on this server")
        else:
            r.raise_for_status()
            d = r.json()
            top = d["results"][0] if d.get("answerable") and d.get("results") else None      # picked passages come first
            print(f"[ask] {step['ask']}\n    -> " + (f"{top['doc']} §{top['section']} (p. {top['page']}, effective "
                  f"{top.get('effective')}): {top['text'][:160]}" if top else "not in the county's documents"))
    elif "handoff" in step:
        r = c.get("/api/handoff")
        print("[handoff]\n" + (r.json().get("text", "") if r.status_code == 200 else f"    -> {r.status_code}"))
    elif "monitor" in step:
        facts = [{"key": k, "value": v, "captured_by": "device", "role": "device", "speaker": "monitor",
                  "confidence": 0.99} for k, v in step["monitor"].items()]
        c.post("/api/facts", json=facts).raise_for_status()
        print(f"[monitor] {step['monitor']}")
    if not a.fast:
        time.sleep(step.get("pause", 2))
s = c.get("/api/state").json()
r = s["readiness"][0] if s["readiness"] else None
print("\nFINAL:", s["summary"], "|", f"{r['label']} {r['done']}/{r['total']}" if r else "",
      "| NEWS2", s["scores"]["news2"]["score"], s["scores"]["news2"]["band"],
      "| RACE", s["scores"]["race"]["score"], "| G.F.A.S.T.", s["scores"]["gfast"]["score"],
      "(complete)" if s["scores"]["gfast"]["complete"] else "(incomplete)", "| alerts:", [x["type"] for x in s["alerts"]])
