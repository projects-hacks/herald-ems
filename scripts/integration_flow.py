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

    health = call(f"{a.url}/api/health")
    print("=== health ===")
    print(f"  stt={health.get('stt_loaded')} extraction={health.get('llm_model')} "
          f"({health.get('llm_available')}) vision={health.get('vision_model')} ({health.get('vision_available')}) "
          f"cloud_ai_calls={health.get('cloud_ai_calls')}")
    if health.get("cloud_ai_calls"):
        BUGS.append(f"cloud_ai_calls is {health['cloud_ai_calls']}, must be 0 (invariant 1: no cloud AI)")

    stack = call(f"{a.url}/api/stack")
    print("\n=== stack as the screen shows it ===")
    # A model listed under `research` in config/stack.yaml is MEANT to read "not served" -- that is the baseline and
    # rollback entry. Only a component the app is actually using may not be missing, so compare against /api/health.
    serving = {health.get("llm_model"), health.get("vision_model")}
    for m in stack["models"]:
        served_as = m.get("served_as")
        label = served_as or "(whisper)"
        print(f"  {label:16s} {m['status']}")
        # The speech-to-text entry has no `served_as` at all: Whisper runs in-process, not behind a ZRT label, and
        # /api/stack computes its status from stt.ready(). Comparing it against the ZRT labels reports a phantom
        # model called "None", which is a bug in this check and not in the stack.
        if served_as is None:
            continue
        if served_as in serving and "not served" in m["status"]:
            BUGS.append(f"/api/stack shows {served_as} as {m['status']!r}, but the app is using it: "
                        f"config/stack.yaml is missing the entry for the component it serves")
        if served_as not in serving and m["status"] == "ready":
            BUGS.append(f"/api/stack shows {served_as} ready, but the app is not using it (serving {serving})")

    print("\n=== 0. egress allow-list (every outbound call goes through it) ===")
    try:
        eg = call(f"{a.url}/api/egress")
        allowed = eg.get("allowed") or eg.get("allow") or eg.get("destinations") or eg
        print(f"  {json.dumps(allowed)[:400]}")
        denied = eg.get("denied") or eg.get("denials") or []
        if denied:
            print(f"  denied so far: {json.dumps(denied)[:300]}")
            BUGS.append(f"egress already recorded {len(denied)} denial(s) before the relay ran: {denied!r:.200}")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read()[:200]!r}")
        BUGS.append(f"/api/egress returned HTTP {e.code}")

    # A FRESH INCIDENT FIRST. Herald deduplicates: a fact already in the incident is not added again. Run this against
    # an incident that already holds the same call -- after a soak that replayed the stroke scenario 163 times, say --
    # and a perfectly healthy extractor yields zero NEW facts, which reads exactly like a broken model. Measured: the
    # extraction returned status "done" in 4 s and added nothing, because all 27 facts were already there.
    print("\n=== starting a fresh incident so `new facts` means something ===")
    try:
        inc = call(f"{a.url}/api/incident", "POST", {})
        print(f"  incident {(inc.get('incident') or inc).get('id', inc)}")
    except urllib.error.HTTPError as e:
        print(f"  could not start one (HTTP {e.code}); counting new facts against the current incident instead")

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
        # Key the facts to THIS upload's photo_id. Matching "any fact with a photo_id" made the POLST step report the
        # previous monitor read's six vitals as its own, in 0.17 s, and then score them against an empty gold and
        # call it a pass -- a false PASS, which is worse than a false failure. The photo_id is stamped on provenance
        # by herald/api/capture.py, so it is the only honest join key.
        def find_photo_id(obj):
            if isinstance(obj, dict):
                if isinstance(obj.get("photo_id"), str):
                    return obj["photo_id"]
                for v in obj.values():
                    got = find_photo_id(v)
                    if got:
                        return got
            elif isinstance(obj, list):
                for v in obj:
                    got = find_photo_id(v)
                    if got:
                        return got
            return None

        photo_id = find_photo_id(out)
        if not photo_id:
            BUGS.append(f"{label}: POST /api/photo returned no photo_id, so its facts cannot be told apart from an "
                        f"earlier photo's")
        pf = [f for f in (out.get("facts") or out.get("added") or [])
              if not photo_id or (f.get("provenance") or {}).get("photo_id") == photo_id]
        if not pf and photo_id:         # same async shape as /api/transcript: wait for the snapshot
            for _ in range(60):
                time.sleep(1)
                snap2 = call(f"{a.url}/api/state")
                cand = [f for f in snap2["facts"].values()
                        if (f.get("provenance") or {}).get("photo_id") == photo_id]
                if cand:
                    pf = cand
                    break
        print(f"  {dt:.2f}s, {len(pf)} facts for photo_id={photo_id}")
        if dt < 0.5 and pf:
            BUGS.append(f"{label} returned {len(pf)} facts in {dt:.2f}s, which is too fast for a vision call: "
                        f"they are probably another photo's")
        show(pf)
        # Whether 0 facts is a defect depends on the gold. For a form the model cannot read, abstaining is the SAFE
        # answer and the documented behaviour (POLST: 3 of 10 read, 7 empty, 0 wrong code_status), and the gold row
        # for such a form lists no facts. Flagging it as a bug would push toward guessing on forms.
        gold_row = None
        gold_file = ROOT / Path(photo).parent / "gold.jsonl"
        if gold_file.exists():
            gold_row = next((json.loads(ln) for ln in gold_file.read_text().splitlines()
                             if json.loads(ln).get("file") == Path(photo).name), None)
        expects_facts = gold_row is None or bool(
            dict(gold_row["facts"]) if isinstance(gold_row["facts"], list) else gold_row["facts"])
        if not pf and expects_facts:
            BUGS.append(f"{label} returned 0 facts while its gold expects some")
        elif not pf:
            print("  0 facts, and the gold expects none: abstention, which is the safe failure for a form")
        elif any(f.get("status") == "confirmed" for f in pf):
            BUGS.append(f"{label} returned a CONFIRMED fact: photo readings must start unconfirmed "
                        f"(AGENTS.md invariant 4)")
        gold_path = ROOT / Path(photo).parent / "gold.jsonl"
        if gold_path.exists():
            want = Path(photo).name
            row = next((json.loads(ln) for ln in gold_path.read_text().splitlines()
                        if json.loads(ln).get("file") == want), None)
            if row is None:
                # "0/0 exact" against an empty gold silently passes. Say the gold is missing instead of scoring air.
                print(f"  no gold row for {want} in {gold_path.relative_to(ROOT)}: not scored here")
            else:
                g = dict(row["facts"]) if isinstance(row["facts"], list) else row["facts"]
                got = {f["key"]: f["value"] for f in pf}
                ok = sum(1 for k, v in g.items() if str(got.get(k)) == str(v))
                print(f"  against gold: {ok}/{len(g)} exact   gold={g}")
                if not g:
                    print("  (the gold row lists no facts: abstention is the expected answer)")
                elif ok < len(g):
                    BUGS.append(f"{label} read {ok}/{len(g)} of gold")

    print("\n=== 4b. one-tap reading confirm (POST /api/readings/{frame_id}/confirm) ===")
    # One monitor frame yields HR/BP/SpO2/RR at once, so the medic confirms the reading as a set. Readings the
    # corroboration rules flag -- a jump past the plausible step, a first reading, a held fact, a label mismatch --
    # come back in `individual` and stay unconfirmed. That is the mechanism that contains an HR/SpO2 label swap
    # (docs/RUN_F_REPORT.md §8, cam_07): a swap shows up as two implausible jumps and each is asked about separately.
    snap = call(f"{a.url}/api/state")
    groups = snap.get("capture_groups") or []
    print(f"  capture_groups: {len(groups)}")
    if not groups:
        # NOT a defect. BatchConfirmation.frame_ids() keys off provenance.frame_id, which the agentic capture reader
        # stamps on frames it grabs from the camera. A manual POST /api/photo has frame_id=null and trigger=null
        # (verified in the snapshot), so it forms no group by design. Exercising this endpoint therefore needs the
        # capture path with a real camera, and this box has no /dev/video*. Say that instead of inventing a bug.
        photo_facts = [f for f in snap["facts"].values() if (f.get("provenance") or {}).get("photo_id")]
        framed = [f for f in photo_facts if (f.get("provenance") or {}).get("frame_id")]
        cams = sorted(Path("/dev").glob("video*"))
        print(f"  {len(photo_facts)} photo facts, {len(framed)} carrying a frame_id; cameras present: "
              f"{[c.name for c in cams] or 'none'}")
        print("  SKIPPED, not failed: one-tap reading confirm groups by provenance.frame_id, which only the camera "
              "capture path stamps. A manual photo upload cannot produce a group.")
        if framed:
            BUGS.append(f"{len(framed)} photo facts carry a frame_id but capture_groups is empty: the grouping "
                        f"is dropping frames it should batch")
        if cams:
            BUGS.append(f"a camera exists ({[c.name for c in cams]}) but this run did not exercise the capture "
                        f"path, so one-tap reading confirm is still unverified end to end")
    for g in groups[:2]:
        print(f"    frame={g.get('frame_id')} trigger={g.get('trigger')} "
              f"batchable={len(g.get('batch_fact_ids') or [])} individual={len(g.get('individual') or [])}")
        for row in (g.get("individual") or [])[:6]:
            print(f"      individual: {json.dumps(row)[:180]}")
    if groups:
        frame = groups[0]["frame_id"]
        try:
            res = call(f"{a.url}/api/readings/{frame}/confirm", "POST", {})
            conf = res.get("confirmed") or []
            indiv = res.get("individual") or []
            print(f"  confirmed {len(conf)} in one tap, {len(indiv)} left for their own look")
            for row in indiv[:6]:
                print(f"    still unconfirmed: {json.dumps(row)[:180]}")
            after = call(f"{a.url}/api/state")
            ids = set(conf)
            bad = [f for f in after["facts"].values() if f.get("id") in ids and f.get("status") != "confirmed"]
            if bad:
                BUGS.append(f"one-tap reading confirm reported {len(conf)} confirmed but {len(bad)} are still not "
                            f"confirmed in the snapshot")
            if not conf and not indiv:
                BUGS.append("one-tap reading confirm returned neither confirmed nor individual rows")
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: {e.read()[:200]!r}")
            BUGS.append(f"POST /api/readings/{{frame_id}}/confirm returned HTTP {e.code}")

    print("\n=== 4c. FHIR R4 export (GET /api/handoff/fhir) ===")
    try:
        fhir = call(f"{a.url}/api/handoff/fhir")
        rt = fhir.get("resourceType")
        entries = fhir.get("entry") or []
        kinds = {}
        for e in entries:
            k = ((e.get("resource") or {}).get("resourceType")) or "?"
            kinds[k] = kinds.get(k, 0) + 1
        print(f"  resourceType={rt} entries={len(entries)} {kinds}")
        if rt != "Bundle":
            BUGS.append(f"/api/handoff/fhir returned resourceType {rt!r}, expected 'Bundle'")
        if not entries:
            BUGS.append("/api/handoff/fhir returned an empty bundle after facts were confirmed")
        # Invariant 4: only confirmed facts leave the vehicle, and the export is a leaving path.
        state = call(f"{a.url}/api/state")
        n_conf = sum(1 for f in state["facts"].values() if f.get("status") == "confirmed")
        print(f"  confirmed facts in the incident: {n_conf}")
        if n_conf == 0 and entries:
            BUGS.append("the FHIR bundle has entries while no fact is confirmed: only confirmed facts may leave")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read()[:200]!r}")
        BUGS.append(f"/api/handoff/fhir returned HTTP {e.code}")

    print("\n=== 5. relay -> ED ===")
    # POST /api/relay/authorize takes a REQUIRED body, {"destination": "<name>"} (herald/api/routes/relay.py
    # Authorize). Calling it with no body returns 422, which looks like a broken relay and is not one. The medic
    # picks a destination on the screen, so take one the county actually offers.
    dest = "Regional"
    try:
        county = call(f"{a.url}/api/county")
        active = county.get("active") or {}
        names = [d.get("name") or d.get("id") for d in (active.get("destinations") or []) if isinstance(d, dict)]
        if names:
            dest = names[0]
        print(f"  destinations offered: {names or '(none listed; using ' + dest + ')'}")
    except urllib.error.HTTPError:
        pass
    try:
        auth = call(f"{a.url}/api/relay/authorize", "POST", {"destination": dest})
        print(f"  authorize -> {dest}: {json.dumps(auth)[:200]}")
    except urllib.error.HTTPError as e:
        print(f"  authorize HTTP {e.code}: {e.read()[:200]!r}")
        BUGS.append(f"relay authorize with destination={dest!r} returned HTTP {e.code}")
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
        # Since 2026-09-25 every outbound call goes through an allow-list, and a denied relay looks exactly like a
        # dead link from the app's side. Name the difference instead of leaving it to guesswork.
        try:
            eg = call(f"{a.url}/api/egress")
            print(f"  egress after the attempt: {json.dumps(eg)[:400]}")
            if eg.get("denied") or eg.get("denials"):
                BUGS.append("the relay was DENIED by the egress allow-list, not dropped by the link: set "
                            "HERALD_ED_URL (allowed automatically) or list the destination in config/egress.yaml")
        except urllib.error.HTTPError:
            pass

    print("\n" + "=" * 70)
    if BUGS:
        print(f"INTEGRATION DEFECTS FOUND: {len(BUGS)}")
        for i, b in enumerate(BUGS, 1):
            print(f"  {i}. {b}")
    else:
        print("NO INTEGRATION DEFECTS: egress, speech, confirm, photo, POLST, one-tap reading confirm, "
              "FHIR export and relay all behaved.")


if __name__ == "__main__":
    main()
