#!/usr/bin/env python3
"""Replay a scenario against a running Herald server (rehearsal, video, regression).

  python scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8100 [--fast] [--no-llm]
  (--no-llm: words only, nothing extracted; there is no rules extractor in the product)
"""
import argparse
import json
import time
from datetime import datetime, timedelta

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("scenario")
ap.add_argument("--url", default="http://localhost:8100")
ap.add_argument("--fast", action="store_true", help="no pauses")
ap.add_argument("--no-llm", action="store_true", help="send the words without extraction (model status off)")
ap.add_argument("--lkw-minutes-ago", type=int, default=64)
a = ap.parse_args()

sc = json.load(open(a.scenario))
lkw = (datetime.now() - timedelta(minutes=a.lkw_minutes_ago)).strftime("%-I:%M")
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
        facts = c.get("/api/state").json()["facts"]
        done = [k for k, f in facts.items() if k.startswith(step["confirm"]) and f["status"] == "unconfirmed"
                and not c.post(f"/api/facts/{f['id']}/confirm").raise_for_status() is None]
        print(f"[tap] confirmed {done}")
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
