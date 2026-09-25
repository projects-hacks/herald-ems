#!/usr/bin/env python3
"""One real end-to-end pass through the running app, printing what came back at every stage.

This is the check no gold score can replace: no 30B had ever run through Herald's own request path. It exercises
speech -> facts -> confirm -> relay -> ED, then the photo and POLST vision paths, against a live app.

    scripts/integration_flow.py --url http://127.0.0.1:8103 --ed http://127.0.0.1:8200

Reports every integration defect it finds rather than only a pass or fail.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUGS: list[str] = []


def call(url: str, method: str = "GET", body: dict | None = None, files: tuple | None = None, timeout: float = 180):
    if files is not None:
        name, path, mode = files
        boundary = "----herald"
        blob = Path(path).read_bytes()
        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\n{mode}\r\n".encode(),
                 f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                 f"filename=\"{Path(path).name}\"\r\nContent-Type: image/jpeg\r\n\r\n".encode(), blob,
                 f"\r\n--{boundary}--\r\n".encode()]
        data = b"".join(parts)
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    else:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"content-type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def show(facts, indent="    "):
    for f in facts:
        print(f"{indent}{f.get('key', '?'):24s} {f.get('value')!r:28s} "
              f"status={f.get('status')} role={f.get('role')} conf={f.get('confidence')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8103")
    ap.add_argument("--ed", default="http://127.0.0.1:8200")
    a = ap.parse_args()

    stack = call(f"{a.url}/api/stack")
    print("=== stack as the screen shows it ===")
    for m in stack["models"]:
        print(f"  {str(m.get('served_as')):16s} {m['status']}")
        if "not served" in m["status"]:
            BUGS.append(f"/api/stack shows {m.get('served_as')} as {m['status']!r}: config/stack.yaml has no "
                        f"herald-f entry, so the AI-stack screen reports the shipped model as missing")

    print("\n=== 1. speech -> facts (the app's own capture path) ===")
    line = ("Valley this is Medic 12, stroke alert. 71 year old female, last known well 0915, "
            "left facial droop, left arm drifts, BP 178 over 96, sat 93, glucose 142, she takes warfarin.")
    # Extraction is ASYNCHRONOUS: /api/transcript returns at once with trace.model.status == "running" and an
    # empty facts list, and the facts land in the snapshot afterwards. A synchronous read of the POST response
    # therefore always sees zero facts, which looks exactly like a broken extractor.
    before = set(call(f"{a.url}/api/state")["facts"])
    t0 = time.perf_counter()
    out = call(f"{a.url}/api/transcript", "POST", {"text": line, "role": "medic", "use_llm": True})
    print(f"  POST returned in {time.perf_counter() - t0:.2f}s with "
          f"trace.model.status={out['transcript']['trace']['model']['status']!r} (async)")
    facts = []
    for _ in range(60):
        time.sleep(1)
        snap = call(f"{a.url}/api/state")
        new = set(snap["facts"]) - before
        tr = next((t for t in snap.get("transcripts", []) if t["id"] == out["transcript"]["id"]), None)
        if new and (tr is None or (tr.get("trace", {}).get("model", {}) or {}).get("status") != "running"):
            facts = [snap["facts"][k] for k in sorted(new)]
            break
    dt = time.perf_counter() - t0
    print(f"  {dt:.2f}s end to end, {len(facts)} facts")
    show(facts)
    if not facts:
        BUGS.append("speech capture through the app produced no facts within 60 s")

    snap = call(f"{a.url}/api/state")
    unconf = [f for f in snap["facts"].values() if f.get("status") == "unconfirmed"]
    print(f"\n=== 2. confirm ===\n  unconfirmed before: {len(unconf)}")
    if unconf:
        target = unconf[0]
        call(f"{a.url}/api/facts/{target['id']}/confirm", "POST", {})
        after = call(f"{a.url}/api/state")
        still = [f for f in after["facts"].values()
                 if f.get("id") == target.get("id") and f["status"] == "unconfirmed"]
        print(f"  confirmed {target['key']}: {'FAILED, still unconfirmed' if still else 'ok'}")
        if still:
            BUGS.append(f"confirming {target['key']} did not change its status")

    for label, photo, mode in (("3. photo (monitor)", "eval/photos/camera_screen/cam_04_handheld_light.jpg", "monitor"),
                               ("4. POLST (form)", "eval/forms_polst/polst_test_0000.jpg", "form")):
        print(f"\n=== {label} ===")
        t0 = time.perf_counter()
        try:
            out = call(f"{a.url}/api/photo", files=("file", ROOT / photo, mode))
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: {e.read()[:200]!r}")
            BUGS.append(f"{label} returned HTTP {e.code}")
            continue
        dt = time.perf_counter() - t0
        pf = out.get("facts") or out.get("added") or []
        if not pf:                      # same async shape as /api/transcript: wait for the snapshot
            seen = set()
            for _ in range(60):
                time.sleep(1)
                snap2 = call(f"{a.url}/api/state")
                cand = [f for f in snap2["facts"].values()
                        if (f.get("provenance") or {}).get("photo_id")]
                if cand and len(cand) != len(seen):
                    seen = set(id(c) for c in cand)
                    pf = cand
                    break
        print(f"  {dt:.2f}s, {len(pf)} facts")
        show(pf)
        if not pf:
            BUGS.append(f"{label} returned 0 facts")
        elif any(f.get("status") == "confirmed" for f in pf):
            BUGS.append(f"{label} returned a CONFIRMED fact: photo readings must start unconfirmed "
                        f"(AGENTS.md invariant 4)")
        gold_path = ROOT / Path(photo).parent / "gold.jsonl"
        if gold_path.exists():
            want = Path(photo).name
            for ln in gold_path.read_text().splitlines():
                r = json.loads(ln)
                if r["file"] == want:
                    g = dict(r["facts"]) if isinstance(r["facts"], list) else r["facts"]
                    got = {f["key"]: f["value"] for f in pf}
                    ok = sum(1 for k, v in g.items() if str(got.get(k)) == str(v))
                    print(f"  against gold: {ok}/{len(g)} exact   gold={g}")
                    if ok < len(g):
                        BUGS.append(f"{label} read {ok}/{len(g)} of gold")
                    break

    print("\n=== 5. relay -> ED ===")
    try:
        auth = call(f"{a.url}/api/relay/authorize", "POST")
        print(f"  authorize: {json.dumps(auth)[:160]}")
    except urllib.error.HTTPError as e:
        print(f"  authorize HTTP {e.code}: {e.read()[:160]!r}")
        BUGS.append(f"relay authorize returned HTTP {e.code}")
    for _ in range(12):
        time.sleep(2)
        ed = call(f"{a.ed}/state", timeout=10)
        inc = ed.get("incidents") or {}
        if inc:
            for iid, rec in inc.items():
                fields = rec.get("fields") or rec.get("facts") or {}
                print(f"  ED incident {iid}: {len(fields)} fields")
                for k, v in list(fields.items())[:12]:
                    print(f"    {k:24s} {v}")
            break
    else:
        print("  ED received nothing after 24 s")
        BUGS.append("relay authorized but the ED receiver got no incident")

    print("\n" + "=" * 70)
    if BUGS:
        print(f"INTEGRATION DEFECTS FOUND: {len(BUGS)}")
        for i, b in enumerate(BUGS, 1):
            print(f"  {i}. {b}")
    else:
        print("NO INTEGRATION DEFECTS: speech, confirm, photo, POLST and relay all behaved.")


if __name__ == "__main__":
    main()
