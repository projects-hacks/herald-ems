#!/usr/bin/env python3
"""Replay a scenario against a running Herald server (rehearsal, video, regression).

  python scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8100 [--fast] [--no-llm]
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
ap.add_argument("--no-llm", action="store_true", help="rules extractor only")
ap.add_argument("--lkw-minutes-ago", type=int, default=64)
a = ap.parse_args()

sc = json.load(open(a.scenario))
lkw = (datetime.now() - timedelta(minutes=a.lkw_minutes_ago)).strftime("%-I:%M")
c = httpx.Client(base_url=a.url, timeout=120)
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
        d = r.json()
        print(f"[{step.get('speaker') or step.get('by', 'medic')}] {text}\n    -> {len(d['facts'])} facts, "
              f"{d['transcript']['extract']} in {time.perf_counter() - t0:.2f}s")
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
      "| RACE", s["scores"]["race"]["score"], "| alerts:", [x["type"] for x in s["alerts"]])
