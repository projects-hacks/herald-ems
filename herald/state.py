"""The patient state engine.

Append-only facts in, a live picture of the patient out. Everything here is
deterministic: checklists, gaps, contradictions, trends, clocks, and published
scores. The language model never computes any of it.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import scores
from . import county
from .checklists import ALERTS, DEFAULT_UNKNOWNS, active_alerts
from .schema import (CONTRADICTION_KEYS, KEYS, CapturedBy, Fact, FactIn, Status,
                     new_id, utcnow)

AUTO_CONFIRM = float(os.getenv("HERALD_AUTO_CONFIRM", "0.85"))
REASSESS_MIN = int(os.getenv("HERALD_REASSESS_MIN", "10"))
LOCAL_TZ = ZoneInfo(os.getenv("HERALD_TZ", "America/Los_Angeles"))

# Significant-change rules for trends (display + alert; not diagnoses).
CHANGE_RULES = {
    "vitals.sbp": lambda a, b: abs(b - a) >= 20 or (a > 90 >= b),
    "vitals.hr": lambda a, b: abs(b - a) >= 20,
    "vitals.spo2": lambda a, b: (a - b) >= 3 or (a >= 92 > b),
    "vitals.rr": lambda a, b: abs(b - a) >= 6,
    "vitals.glucose": lambda a, b: abs(b - a) >= 50,
}
CHANGE_RULE_TEXT = {
    "vitals.sbp": "SBP changed by 20 mmHg or more, or dropped to 90 or below",
    "vitals.hr": "HR changed by 20/min or more",
    "vitals.spo2": "SpO2 fell by 3 points or more, or dropped below 92%",
    "vitals.rr": "RR changed by 6/min or more",
    "vitals.glucose": "Glucose changed by 50 mg/dL or more",
}


def _norm(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(sorted(str(x).strip().lower() for x in v))
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _coerce(key: str, value: Any) -> Any:
    t = KEYS[key]["type"]
    if value is None:
        return None
    try:
        if t == "int":
            return int(round(float(value)))
        if t == "float":
            return round(float(value), 1)
        if t == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("true", "yes", "y", "1", "witnessed", "on")
            return bool(value)
        if t == "list":
            if isinstance(value, str):
                return [] if value.strip().lower() in ("none", "nkda", "no known allergies", "") else [value.strip()]
            return [str(x).strip() for x in value]
        return str(value).strip()
    except (TypeError, ValueError):
        raise ValueError(f"cannot coerce {value!r} to {t} for {key}")


def parse_clock(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """'1:40', '13:40', '1:40 pm', '0140' -> most recent past local time today/yesterday."""
    now = (now or utcnow()).astimezone(LOCAL_TZ)
    s = str(text).strip().lower().replace(".", "")
    ampm = None
    for tag in ("am", "pm"):
        if s.endswith(tag):
            ampm, s = tag, s[: -len(tag)].strip()
    if ":" in s:
        hh, mm = s.split(":", 1)
    elif s.isdigit() and len(s) in (3, 4):
        hh, mm = s[:-2], s[-2:]
    elif s.isdigit():
        hh, mm = s, "0"
    else:
        return None
    try:
        h, m = int(hh), int(mm)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    candidates = []
    hours = [h]
    if ampm == "pm" and h < 12:
        hours = [h + 12]
    elif ampm == "am" and h == 12:
        hours = [0]
    elif ampm is None and h <= 12:
        hours = [h % 12, h % 12 + 12]
    for hr in hours:
        for day in (0, -1):
            c = (now + timedelta(days=day)).replace(hour=hr, minute=m, second=0, microsecond=0)
            if c <= now + timedelta(minutes=1):
                candidates.append(c)
    return max(candidates) if candidates else None


class Incident:
    def __init__(self, dispatch: Optional[str] = None):
        self.id = new_id("inc")
        self.dispatch = dispatch
        self.started = utcnow()
        self.facts: list[Fact] = []
        self.transcripts: list[dict] = []
        self.news2_history: list[dict] = []
        self.ed_sync: dict[str, dict] = {}   # key -> {"status": sent|queued, "seq": int}
        self.lock = threading.RLock()

    # ---------- ingest ----------
    @staticmethod
    def validate(fin: FactIn) -> None:
        """Raise ValueError if `ingest` would reject this fact (lets a batch be all-or-nothing)."""
        if fin.key not in KEYS:
            raise ValueError(f"unknown key {fin.key}")
        value = _coerce(fin.key, fin.value)
        bounds = KEYS[fin.key].get("range")
        if bounds and value is not None and not (bounds[0] <= value <= bounds[1]):
            raise ValueError(f"implausible {fin.key} {value!r}: outside {bounds[0]}-{bounds[1]}")

    def ingest(self, fin: FactIn, record: bool = True) -> Fact:
        self.validate(fin)
        with self.lock:
            value = _coerce(fin.key, fin.value)
            prev = self.latest(fin.key)
            status = self._initial_status(fin, prev, value)
            data = fin.model_dump()
            data["value"] = value
            fact = Fact(**data, id=new_id("f"), ts=utcnow(), status=status,
                        previous_value=prev.value if prev else None,
                        previous_ts=prev.ts if prev else None)
            self.facts.append(fact)
            if record:
                self._record_news2()
            return fact

    def _initial_status(self, fin: FactIn, prev: Optional[Fact], value: Any) -> Status:
        meta = KEYS[fin.key]
        if meta.get("require_tap"):
            return Status.unconfirmed
        if fin.captured_by in (CapturedBy.camera, CapturedBy.other):
            return Status.unconfirmed
        if (fin.key in CONTRADICTION_KEYS and prev is not None
                and _norm(prev.value) != _norm(value)):
            return Status.unconfirmed
        if fin.confidence >= AUTO_CONFIRM:
            return Status.confirmed
        return Status.unconfirmed

    def set_status(self, fact_id: str, status: Status) -> Fact:
        with self.lock:
            for f in self.facts:
                if f.id == fact_id:
                    f.status = status
                    self._record_news2()
                    return f
        raise KeyError(fact_id)

    # ---------- queries ----------
    def history(self, key: str, confirmed_only: bool = False) -> list[Fact]:
        return [f for f in self.facts if f.key == key and f.status != Status.rejected
                and (not confirmed_only or f.status == Status.confirmed)]

    def latest(self, key: str, confirmed_only: bool = False) -> Optional[Fact]:
        h = self.history(key, confirmed_only)
        return h[-1] if h else None

    def values(self, confirmed_only: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, meta in KEYS.items():
            h = self.history(key, confirmed_only)
            if not h:
                continue
            if meta.get("merge") == "accumulate":
                seen, merged = set(), []
                for f in h:
                    for x in (f.value or []):
                        if _norm(x) not in seen:
                            seen.add(_norm(x))
                            merged.append(x)
                out[key] = merged
            else:
                out[key] = h[-1].value
        return out

    def commit(self) -> None:
        """Call after ingesting a batch (one utterance) so scores are recorded once per utterance."""
        with self.lock:
            self._record_news2()

    def _record_news2(self) -> None:
        n = scores.news2(self.values(confirmed_only=True))
        last = self.news2_history[-1] if self.news2_history else None
        if last is None or (last["score"], last["complete"]) != (n["score"], n["complete"]):
            self.news2_history.append({"ts": utcnow().isoformat(), "score": n["score"],
                                       "complete": n["complete"], "band": n["band"]})

    # ---------- snapshot ----------
    def snapshot(self) -> dict:
        with self.lock:
            now = utcnow()
            vals = self.values(confirmed_only=True)
            all_vals = self.values(confirmed_only=False)
            race = scores.race(vals)
            gfast = scores.gfast(vals)
            news = scores.news2(vals)
            triage = scores.field_triage(vals)
            cty = county.active()
            complaint = all_vals.get("complaint.chief")
            exam_prefix = {"@race": "exam.race.", "@gfast": "exam.gfast."}
            scale_done = {"@race": race["complete"], "@gfast": gfast["complete"]}
            started = {k: any(x.startswith(pre) for x in all_vals) for k, pre in exam_prefix.items()}
            has_race = started["@race"] or started["@gfast"]
            alert_ids = active_alerts(self.dispatch, complaint, has_race)

            readiness = []
            for aid in alert_ids:
                a = ALERTS[aid]
                items = []
                checklist = cty["stroke"]["checklist"] if aid == "stroke" else a["items"]
                for key, label in checklist:
                    if key in exam_prefix:
                        state = "done" if scale_done[key] else ("pending" if started[key] else "missing")
                    elif key in vals:
                        state = "done"
                    elif key in all_vals:
                        state = "pending"
                    else:
                        state = "missing"
                    items.append({"key": key, "label": label, "state": state})
                done = sum(i["state"] == "done" for i in items)
                readiness.append({"id": aid, "label": a["label"], "done": done,
                                  "total": len(items), "ready": done == len(items), "items": items})

            # needs attention: missing measurements vs not-yet-asked history
            missing, unknown, seen = [], [], set()

            def add(key: str, label: str):
                if key in seen or key in vals:
                    return
                seen.add(key)
                kind = KEYS.get(key, {}).get("kind", "measure") if not key.startswith("@") else "measure"
                pending = key in all_vals or started.get(key, False)
                entry = {"key": key, "label": label, "pending_confirm": pending}
                (unknown if kind == "history" else missing).append(entry)

            for r in readiness:
                for i in r["items"]:
                    if i["state"] != "done":
                        add(i["key"], i["label"])
            for label in news["missing"]:
                key = next(k for k, l, _ in scores.NEWS2_PARAMS if l == label)
                add(key, f"{KEYS[key]['label']} (for NEWS2)")
            seeds = DEFAULT_UNKNOWNS + [u for aid in alert_ids for u in ALERTS[aid]["unknowns"]]
            for key in seeds:
                add(key, KEYS[key]["label"])

            # trends
            changed = []
            for key, rule in CHANGE_RULES.items():
                h = self.history(key, confirmed_only=True)
                if len(h) >= 2:
                    series = [f.value for f in h]
                    sig = rule(series[-2], series[-1])
                    changed.append({"key": key, "label": KEYS[key]["label"], "series": series,
                                    "times": [f.ts.isoformat() for f in h],
                                    "delta": series[-1] - series[0],
                                    "direction": "up" if series[-1] > series[-2] else
                                                 ("down" if series[-1] < series[-2] else "flat"),
                                    "significant": sig})

            # alerts
            alerts = []
            for key in CONTRADICTION_KEYS:
                h = self.history(key)
                if len(h) >= 2 and _norm(h[-1].value) != _norm(h[-2].value) \
                        and h[-1].status == Status.unconfirmed:
                    alerts.append({"type": "contradiction", "key": key, "label": KEYS[key]["label"],
                                   "confirm_fact_id": h[-1].id,
                                   "facts": [self._fact_view(f) for f in h[-2:]]})
            for c in changed:
                if c["significant"]:
                    alerts.append({"type": "significant_change", "key": c["key"], "label": c["label"],
                                   "series": c["series"]})
            complete_hist = [x for x in self.news2_history if x["complete"]]
            if len(complete_hist) >= 2:
                a, b = complete_hist[-2], complete_hist[-1]
                if b["score"] - a["score"] >= 2 or (b["band"] in ("medium", "high") and b["band"] != a["band"]):
                    alerts.append({"type": "news2_rise", "label": "NEWS2", "from": a["score"],
                                   "to": b["score"], "band": b["band"]})
            if race["complete"] and race["positive"]:
                alerts.append({"type": "race_positive", "label": "RACE", "score": race["score"]})
            if "GFAST" in cty["stroke"]["scales"] and gfast["complete"]:
                rule = cty["stroke"]["routing"].get("gfast_4" if gfast["positive"] else "gfast_0_3")
                if gfast["positive"]:
                    alerts.append({"type": "gfast_positive", "label": "G.F.A.S.T.", "score": gfast["score"],
                                   "county_rule": rule, "county": cty["name"]})
            for f in self.facts:
                if f.key == "code_status" and f.status == Status.unconfirmed:
                    alerts.append({"type": "confirm_required", "key": f.key, "label": KEYS[f.key]["label"],
                                   "confirm_fact_id": f.id, "facts": [self._fact_view(f)]})

            # clocks
            clocks = [{"id": "scene", "label": "Scene time", "since": self.started.isoformat(),
                       "seconds": int((now - self.started).total_seconds())}]
            lkw = self.latest("stroke.lkw")
            if lkw:
                t = parse_clock(lkw.value, now)
                if t:
                    clocks.append({"id": "lkw", "label": f"LKW {t.strftime('%H:%M')}",
                                   "since": t.isoformat(),
                                   "seconds": int((now - t).total_seconds()),
                                   "confirmed": lkw.status == Status.confirmed})
            eta = self.latest("transport.eta_min")
            if eta:
                arrive = eta.ts + timedelta(minutes=eta.value)
                clocks.append({"id": "eta", "label": "ETA", "until": arrive.isoformat(),
                               "seconds": int((arrive - now).total_seconds())})
            vit = [f for f in self.facts if f.key.startswith("vitals.") and f.status == Status.confirmed]
            if vit:
                every = int(os.getenv("HERALD_REASSESS_MIN") or cty.get("reassess_min", REASSESS_MIN))
                due = vit[-1].ts + timedelta(minutes=every)
                clocks.append({"id": "reassess", "label": f"Repeat vitals (every {every} min)",
                               "until": due.isoformat(), "seconds": int((due - now).total_seconds())})

            latest_facts = {}
            for f in self.facts:
                if f.status != Status.rejected:
                    latest_facts[f.key] = self._fact_view(f)
            summary_bits = [str(all_vals[k]) for k in ("patient.age",) if k in all_vals]
            if "patient.sex" in all_vals:
                summary_bits.append(str(all_vals["patient.sex"]).upper()[:1])
            return {
                "incident": {"id": self.id, "dispatch": self.dispatch, "started": self.started.isoformat()},
                "summary": " ".join(summary_bits) + (f" · {complaint}" if complaint else ""),
                "readiness": readiness,
                "needs_attention": {"missing": missing, "unknown": unknown},
                "changed": changed,
                "scores": {"news2": news, "news2_history": self.news2_history, "race": race, "gfast": gfast,
                           "field_triage": triage,
                           "stroke_scales": cty["stroke"]["scales"], "primary_stroke_scale": cty["stroke"]["primary_scale"]},
                "county": {"id": cty["id"], "name": cty["name"]},
                "alerts": alerts,
                "clocks": clocks,
                "facts": latest_facts,
                "timeline": [self._fact_view(f) for f in self.facts[-60:]],
                "transcripts": self.transcripts[-20:],
                "ed_sync": self.ed_sync,
                "counters": {"facts": len(self.facts), "cloud_ai_calls": 0},
            }

    @staticmethod
    def _fact_view(f: Fact) -> dict:
        d = f.model_dump(mode="json")
        d["label"] = KEYS[f.key]["label"]
        d["unit"] = f.unit or KEYS[f.key].get("unit")
        return d
