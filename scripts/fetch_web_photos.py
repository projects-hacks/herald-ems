#!/usr/bin/env python3
"""Collect openly licensed photographs of real prehospital/bedside monitors for the photo bench (test only).

Herald's photo test sets are synthetic (`eval/photos`) or taken by the team (`data/photos/real`). This adds a third
kind: photographs of **real** monitors taken by other people, in other lighting, at other angles — the closest we can
get to "a screen the model has never seen" without a field trial.

Only Wikimedia Commons files whose licence is public domain or a permissive Creative Commons licence are kept, and
the licence, author and URL of every file are recorded in `sources.jsonl`. Most hits are US federal works (DoD
training and humanitarian-mission photography), which are public domain.

    python scripts/fetch_web_photos.py --out data/photos/web            # collect candidates + download
    python scripts/fetch_web_photos.py --out data/photos/web --dry-run  # list what it would fetch

The answer key (`labels.jsonl`) is written **by hand** after looking at each image: only values that are clearly
readable, nothing inferred. Images are gitignored; the set is never used for training.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "HeraldEMS-research/1.0 (hackathon project; contact: team via GitHub projects-hacks/herald-ems)"

# Phrases that actually turn up photographs of a screen with numbers on it, rather than product shots of a device.
QUERIES = [
    '"vital signs monitor"',
    '"patient monitor" hospital',
    '"cardiac monitor" patient',
    'defibrillator monitor display',
    'LIFEPAK',
    '"Propaq" monitor',
    'ZOLL monitor',
    '"pulse oximeter" display reading',
    'intensive care monitor screen',
    'ambulance patient monitor',
]

# Licence templates we accept. Commons reports these in imageinfo extmetadata LicenseShortName.
OK_LICENCE = ("public domain", "pd-", "cc0", "cc by", "cc-by", "attribution")
REJECT = ("non-free", "fair use", "nd", "noderivs")


_last_call = [0.0]


def api(params: dict, tries: int = 5) -> dict:
    """One API call, throttled to ~1 request/second and retried on 429 — Commons rate-limits scripted clients."""
    params = {**params, "format": "json"}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        wait = max(0.0, 1.1 - (time.monotonic() - _last_call[0]))
        if wait:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            back = 5 * (attempt + 1)
            print(json.dumps({"rate_limited": e.code, "sleeping_s": back}), flush=True)
            time.sleep(back)
    raise RuntimeError("unreachable")


_last_dl = [0.0]


def fetch_file(url: str, gap: float = 5.0, tries: int = 4) -> bytes:
    """Download one image, at most one every `gap` seconds, retrying on 429/503.

    `upload.wikimedia.org` rate-limits harder than the API: the first attempt at this set got two files and then a
    wall of `HTTP Error 429`. The API throttle above does not cover these requests, they go to a different host.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        wait = max(0.0, gap - (time.monotonic() - _last_dl[0]))
        if wait:
            time.sleep(wait)
        _last_dl[0] = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            back = 15 * (attempt + 1)
            print(json.dumps({"rate_limited": e.code, "sleeping_s": back}), flush=True)
            time.sleep(back)
    raise RuntimeError("unreachable")


def search(query: str, limit: int = 30) -> list[str]:
    out = api({"action": "query", "list": "search", "srsearch": f"filetype:bitmap {query}",
               "srnamespace": 6, "srlimit": limit})
    return [h["title"] for h in out.get("query", {}).get("search", [])]


def info(titles: list[str]) -> dict:
    """imageinfo (url, size, licence, author) for up to 50 titles at a time."""
    got = {}
    for i in range(0, len(titles), 50):
        out = api({"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "imageinfo",
                   "iiprop": "url|size|extmetadata|mime"})
        for page in out.get("query", {}).get("pages", {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            got[page["title"]] = {
                "title": page["title"],
                "url": ii.get("url"),
                "descriptionurl": ii.get("descriptionurl"),
                "mime": ii.get("mime"),
                "width": ii.get("width"), "height": ii.get("height"),
                "licence": (meta.get("LicenseShortName", {}) or {}).get("value", ""),
                "author": _strip(( meta.get("Artist", {}) or {}).get("value", "")),
                "credit": _strip((meta.get("Credit", {}) or {}).get("value", "")),
                "description": _strip((meta.get("ImageDescription", {}) or {}).get("value", "")),
            }
    return got


def _strip(html: str) -> str:
    out, depth = [], 0
    for ch in html or "":
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())


# The searches also match computer displays ("monitor") and outdoor AED cabinets ("defibrillator"), which show no
# patient values at all. Rejecting them by name keeps the set honest instead of padding it with unusable images.
NOT_MEDICAL = ("dell ", "benq", "ibm-", "ibm ", "nixdorf", "ila 2010", "crvd", "lcd colour monitor",
               "phone and post box", "post box", "telephone box", "at nuthurst", "samsung", "asus", "acer",
               "eizo", "iiyama", "philips 1", "crt monitor")
# Words that suggest a screen with patient values, rather than a device sitting in a box.
MEDICAL_HINT = ("vital", "monitor/defib", "defibrillator", "patient monitor", "cardiac monitor", "propaq",
                "lifepak", "zoll", "ecg", "ekg", "nibp", "spo2", "casualty", "medic", "hospital", "ambulance",
                "corpsman", "icu", "intensive care")


def acceptable(rec: dict) -> bool:
    lic = (rec.get("licence") or "").lower()
    if not rec.get("url") or not (rec.get("mime") or "").startswith("image/"):
        return False
    if any(bad in lic for bad in REJECT):
        return False
    if not any(good in lic for good in OK_LICENCE):
        return False
    hay = f"{rec.get('title','')} {rec.get('description','')}".lower()
    if any(bad in hay for bad in NOT_MEDICAL):
        return False
    return any(h in hay for h in MEDICAL_HINT)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/photos/web")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()
    out = Path(a.out)

    titles: list[str] = []
    for q in QUERIES:
        try:
            found = search(q)
        except Exception as e:
            print(json.dumps({"query": q, "error": f"{type(e).__name__}: {e}"}))
            continue
        new = [t for t in found if t not in titles]
        titles += new
        print(json.dumps({"query": q, "hits": len(found), "new": len(new)}), flush=True)

    recs = info(titles)
    keep = [r for r in recs.values() if acceptable(r)]
    keep.sort(key=lambda r: -(r.get("width") or 0) * (r.get("height") or 0))
    keep = keep[:a.max]
    print(json.dumps({"candidates": len(recs), "acceptable_licence": len(keep)}, indent=1))
    for r in keep:
        print(json.dumps({"licence": r["licence"], "px": f"{r['width']}x{r['height']}",
                          "title": r["title"], "desc": r["description"][:110]}, ensure_ascii=False))
    if a.dry_run:
        return

    out.mkdir(parents=True, exist_ok=True)

    # Resume by Commons title, not by index: the search can return a slightly different set on a later run, so
    # `web_00` from the first attempt is not guaranteed to be the first record this time.
    done: dict[str, str] = {}
    src_path = out / "sources.jsonl"
    if src_path.exists():
        for line in src_path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if (out / rec["file"]).exists():
                done[rec["title"]] = rec["file"]
    used = set(done.values())

    written: list[dict] = []
    for i, r in enumerate(keep):
        ext = Path(urllib.parse.urlparse(r["url"]).path).suffix.lower() or ".jpg"
        name = done.get(r["title"])
        if name:
            print(json.dumps({"kept": name, "title": r["title"]}), flush=True)
        else:
            name = f"web_{i:02d}{ext}"
            while name in used:                      # a resumed file may already hold this index
                i += 1
                name = f"web_{i:02d}{ext}"
            try:
                (out / name).write_bytes(fetch_file(r["url"]))
            except Exception as e:
                print(json.dumps({"download_failed": r["title"], "error": str(e)[:120]}), flush=True)
                continue
            print(json.dumps({"saved": name, "licence": r["licence"]}), flush=True)
        used.add(name)
        written.append({"file": name, "url": r["descriptionurl"] or r["url"],
                        "direct_url": r["url"], "licence": r["licence"], "author": r["author"],
                        "credit": r["credit"], "title": r["title"],
                        "description": r["description"], "px": f"{r['width']}x{r['height']}"})

    written.sort(key=lambda rec: rec["file"])
    with open(src_path, "w") as fh:
        for rec in written:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\nwrote {src_path} ({len(written)} files) — now write labels.jsonl BY HAND after viewing each image")


if __name__ == "__main__":
    main()
