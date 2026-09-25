#!/usr/bin/env python3
"""Read REAL camera photos in monitor mode and score them against their hand-written labels.

Why this is separate from the synthetic bench: `eval/photos/monitor_01_dark.jpg` is a 1024x768 render with
`degradations: []` and no EXIF. Reading it proves the model can parse a monitor *layout*. It does not show that the
model can read a device through a phone camera with glare, tilt, moire, odd angles and real lighting — which is the
capability continuous monitor-watch actually needs, and the only thing that justifies claiming it.

`data/photos/real/` is 97 photographs taken by people (a real patient's oximeter in 2021, watches, thermometers,
phone health apps) with labels written by hand from what a person could read. There are no real bedside-monitor
photographs in the set, so "monitor mode on a real device" here means an oximeter, a watch or a thermometer.

    scripts/run_job.py --name read-real --need-gib 12 -- python scripts/read_real_photos.py --limit 8

Prints every value read next to its label, so a fast wrong answer cannot look like a pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="data/photos/real")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--device", default=None, help="only this device substring, e.g. 'oximeter'")
    a = ap.parse_args()

    from herald.config.settings import get_settings
    from herald.models.llm_client import LocalLLMClient
    from herald.models.vision import VisionReader

    s = get_settings()
    reader = VisionReader(LocalLLMClient(s.llm_url, s.vision_model), None)
    root = ROOT / a.dir
    rows = [json.loads(ln) for ln in (root / "labels.jsonl").read_text().splitlines() if ln.strip()]
    rows = [r for r in rows if r.get("mode") == "monitor" and (root / r["file"]).exists()]
    if a.device:
        rows = [r for r in rows if a.device.lower() in (r.get("device") or "").lower()]
    # Hardest first: the ones a human flagged as needing a second look.
    rows.sort(key=lambda r: (not r.get("needs_check"), r["file"]))
    rows = rows[:a.limit]

    print(f"vision model: {reader.model.model_name()}   photos: {len(rows)}   dir: {a.dir}\n")
    tot_gold = tot_ok = tot_missed = tot_wrong = tot_invented = 0
    per_photo = []
    for r in rows:
        gold = r["facts"]
        t0 = time.perf_counter()
        facts = reader.read((root / r["file"]).read_bytes(), "monitor", r["file"])
        dt = time.perf_counter() - t0
        got = {f.key: f.value for f in facts}
        ok = [k for k, v in gold.items() if str(got.get(k)) == str(v)]
        wrong = {k: (got[k], v) for k, v in gold.items() if k in got and str(got[k]) != str(v)}
        missed = [k for k in gold if k not in got]
        invented = [k for k in got if k not in gold]
        tot_gold += len(gold); tot_ok += len(ok); tot_missed += len(missed)
        tot_wrong += len(wrong); tot_invented += len(invented)
        flag = "needs_check" if r.get("needs_check") else ""
        print(f"  {r['file']}  [{r.get('device')}] {flag}  {dt:.1f}s")
        if r.get("note"):
            print(f"    note: {r['note']}")
        for k, v in gold.items():
            g = got.get(k, "MISSED")
            print(f"    {k:22s} read={str(g):>8s}  label={str(v):>8s}  {'ok' if str(g) == str(v) else 'WRONG'}")
        for k in invented:
            print(f"    {k:22s} read={str(got[k]):>8s}  label={'—':>8s}  NOT IN LABEL"
                  + ("  (in the label's ignore list)" if any(k.split('.')[-1] in i.lower()
                                                             for i in r.get("ignore", [])) else ""))
        per_photo.append({"file": r["file"], "exact": f"{len(ok)}/{len(gold)}", "invented": len(invented)})
        print()

    print(json.dumps({"photos": len(rows), "labelled_values": tot_gold, "read_exactly_right": tot_ok,
                      "wrong_value": tot_wrong, "missed": tot_missed, "not_in_label": tot_invented,
                      "value_accuracy": round(tot_ok / tot_gold, 3) if tot_gold else None,
                      "per_photo": per_photo}, indent=1))
    if tot_gold and tot_ok == tot_gold and not tot_invented:
        print("\nREAD EVERY REAL PHOTO CORRECTLY, nothing invented.")


if __name__ == "__main__":
    main()
