"""The projection from an incident's facts to the patient picture every screen shows.

Deterministic: checklist readiness, gaps, trends, contradictions, clocks, and published scores. Everything
clinical comes from injected, config-driven parts (scales, checklists, county, trend rules); this module only
assembles them. The language model never computes any of it.
"""
from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

from ..checklists import ChecklistEngine
from ..config import get_settings
from ..config.county import SCALE_IDS, CountyRegistry
from ..scoring import ScaleRegistry, default_scales
from .clock import parse_clock
from .schema import Fact, Status, utcnow
from .trends import TrendRules
from .vocabulary import Vocabulary, default_vocabulary, norm_value

SCORE_HISTORY = "news2"          # the score whose history drives the "rose" alert


class Projector:
    def __init__(self, vocabulary: Vocabulary, scales: ScaleRegistry, checklists: ChecklistEngine,
                 counties: CountyRegistry, trends: TrendRules, tz: ZoneInfo, reassess_min: Optional[int] = None):
        self.vocab, self.scales, self.checklists = vocabulary, scales, checklists
        self.counties, self.trends, self.tz, self.reassess_override = counties, trends, tz, reassess_min

    # ---------- score history (called on commit) ----------
    def record_scores(self, inc) -> None:
        n = self.scales[SCORE_HISTORY].evaluate(inc.values(confirmed_only=True))
        last = inc.news2_history[-1] if inc.news2_history else None
        if last is None or (last["score"], last["complete"]) != (n["score"], n["complete"]):
            inc.news2_history.append({"ts": utcnow().isoformat(), "score": n["score"],
                                      "complete": n["complete"], "band": n["band"]})

    def fact_view(self, f: Fact) -> dict:
        d = f.model_dump(mode="json")
        d["label"] = self.vocab.label(f.key)
        d["unit"] = f.unit or self.vocab.meta(f.key).get("unit")
        return d

    # ---------- the picture ----------
    def snapshot(self, inc) -> dict:
        with inc.lock:
            now = utcnow()
            county = self.counties.active
            vals, all_vals = inc.values(confirmed_only=True), inc.values(confirmed_only=False)
            results = self.scales.evaluate_all(vals)
            complaint = all_vals.get("complaint.chief")
            item_scales = {f"@{s.id}": s for s in self.scales.item_scales()}
            started = {ref: any(k.startswith(s.key_prefix) for k in all_vals) for ref, s in item_scales.items()}
            alert_ids = self.checklists.active(inc.dispatch, complaint, any(started.values()))
            readiness = self._readiness(alert_ids, vals, all_vals, results, started)
            missing, unknown = self._needs_attention(readiness, alert_ids, vals, all_vals, results, started)
            changed = self._trends(inc)
            alerts = self._alerts(inc, changed, results, county)
            summary = " ".join([str(all_vals["patient.age"])] if "patient.age" in all_vals else [])
            if "patient.sex" in all_vals:
                summary = f"{summary} {str(all_vals['patient.sex']).upper()[:1]}".strip()
            latest = {f.key: self.fact_view(f) for f in inc.facts if f.status != Status.rejected}
            return {
                "incident": {"id": inc.id, "dispatch": inc.dispatch, "started": inc.started.isoformat()},
                "summary": summary + (f" · {complaint}" if complaint else ""),
                "readiness": readiness,
                "needs_attention": {"missing": missing, "unknown": unknown},
                "changed": changed,
                "scores": {"news2": results["news2"], "news2_history": inc.news2_history, "race": results["race"],
                           "gfast": results["gfast"], "field_triage": results["field_triage"],
                           "stroke_scales": county["stroke"]["scales"],
                           "primary_stroke_scale": county["stroke"]["primary_scale"]},
                "county": {"id": county["id"], "name": county["name"]},
                "alerts": alerts,
                "clocks": self._clocks(inc, now, county),
                "facts": latest,
                "timeline": [self.fact_view(f) for f in inc.facts[-60:]],
                "transcripts": inc.transcripts[-20:],
                "ed_sync": inc.ed_sync,
                "counters": {"facts": len(inc.facts), "cloud_ai_calls": 0},
            }

    def _readiness(self, alert_ids, vals, all_vals, results, started) -> list[dict]:
        out = []
        for aid in alert_ids:
            items = []
            for key, label in self.checklists.items(aid):
                if key.startswith("@"):
                    state = "done" if results[key[1:]]["complete"] else ("pending" if started[key] else "missing")
                else:
                    state = "done" if key in vals else ("pending" if key in all_vals else "missing")
                items.append({"key": key, "label": label, "state": state})
            done = sum(i["state"] == "done" for i in items)
            out.append({"id": aid, "label": self.checklists.label(aid), "done": done, "total": len(items),
                        "ready": done == len(items), "items": items})
        return out

    def _needs_attention(self, readiness, alert_ids, vals, all_vals, results, started):
        missing, unknown, seen = [], [], set()

        def add(key: str, label: str):
            if key in seen or key in vals:
                return
            seen.add(key)
            kind = "measure" if key.startswith("@") else self.vocab.meta(key).get("kind", "measure")
            entry = {"key": key, "label": label, "pending_confirm": key in all_vals or started.get(key, False)}
            (unknown if kind == "history" else missing).append(entry)

        for r in readiness:
            for i in r["items"]:
                if i["state"] != "done":
                    add(i["key"], i["label"])
        news2 = self.scales["news2"]
        for label in results["news2"]["missing"]:
            key = next(p["key"] for p in news2.parameters if p["label"] == label)
            add(key, f"{self.vocab.label(key)} (for NEWS2)")
        seeds = self.checklists.default_unknowns + [u for aid in alert_ids for u in self.checklists.unknowns(aid)]
        for key in seeds:
            add(key, self.vocab.label(key))
        return missing, unknown

    def _trends(self, inc) -> list[dict]:
        changed = []
        for key in self.trends.keys():
            h = inc.history(key, confirmed_only=True)
            if len(h) >= 2:
                series = [f.value for f in h]
                changed.append({"key": key, "label": self.vocab.label(key), "series": series,
                                "times": [f.ts.isoformat() for f in h], "delta": series[-1] - series[0],
                                "direction": "up" if series[-1] > series[-2] else
                                             ("down" if series[-1] < series[-2] else "flat"),
                                "significant": self.trends.significant(key, series[-2], series[-1])})
        return changed

    def _alerts(self, inc, changed, results, county) -> list[dict]:
        alerts = []
        for key in sorted(self.vocab.contradiction_keys):
            h = inc.history(key)
            if len(h) >= 2 and norm_value(h[-1].value) != norm_value(h[-2].value) and h[-1].status == Status.unconfirmed:
                alerts.append({"type": "contradiction", "key": key, "label": self.vocab.label(key),
                               "confirm_fact_id": h[-1].id, "facts": [self.fact_view(f) for f in h[-2:]]})
        for c in changed:
            if c["significant"]:
                alerts.append({"type": "significant_change", "key": c["key"], "label": c["label"],
                               "series": c["series"]})
        hist = [x for x in inc.news2_history if x["complete"]]
        if len(hist) >= 2:
            a, b = hist[-2], hist[-1]
            if b["score"] - a["score"] >= 2 or (b["band"] in ("medium", "high") and b["band"] != a["band"]):
                alerts.append({"type": "news2_rise", "label": "NEWS2", "from": a["score"], "to": b["score"],
                               "band": b["band"]})
        for name in county["stroke"]["scales"]:
            scale = self.scales[SCALE_IDS[name]]
            r = results[scale.id]
            if r["complete"] and r["positive"]:
                alert = {"type": scale.alert_type, "label": scale.name, "score": r["score"]}
                rule = county["stroke"].get("routing", {}).get(scale.id, {}).get("positive")
                if rule:
                    alert.update(county_rule=rule, county=county["name"])
                alerts.append(alert)
        for f in inc.facts:
            if self.vocab.meta(f.key).get("require_tap") and f.status == Status.unconfirmed:
                alerts.append({"type": "confirm_required", "key": f.key, "label": self.vocab.label(f.key),
                               "confirm_fact_id": f.id, "facts": [self.fact_view(f)]})
        return alerts

    def _clocks(self, inc, now, county) -> list[dict]:
        clocks = [{"id": "scene", "label": "Scene time", "since": inc.started.isoformat(),
                   "seconds": int((now - inc.started).total_seconds())}]
        lkw = inc.latest("stroke.lkw")
        if lkw and (t := parse_clock(lkw.value, self.tz, now)):
            clocks.append({"id": "lkw", "label": f"LKW {t.strftime('%H:%M')}", "since": t.isoformat(),
                           "seconds": int((now - t).total_seconds()), "confirmed": lkw.status == Status.confirmed})
        eta = inc.latest("transport.eta_min")
        if eta:
            arrive = eta.ts + timedelta(minutes=eta.value)
            clocks.append({"id": "eta", "label": "ETA", "until": arrive.isoformat(),
                           "seconds": int((arrive - now).total_seconds())})
        vit = [f for f in inc.facts if f.key.startswith("vitals.") and f.status == Status.confirmed]
        if vit:
            every = self.reassess_override or county.get("reassess_min", 10)
            due = vit[-1].ts + timedelta(minutes=every)
            clocks.append({"id": "reassess", "label": f"Repeat vitals (every {every} min)", "until": due.isoformat(),
                           "seconds": int((due - now).total_seconds())})
        return clocks


def build_projector(settings, counties: CountyRegistry) -> Projector:
    vocab = default_vocabulary()
    return Projector(vocab, default_scales(), ChecklistEngine.from_config(counties), counties,
                     TrendRules.from_config(), ZoneInfo(settings.timezone), settings.reassess_min)


@lru_cache(maxsize=1)
def default_counties() -> CountyRegistry:
    return CountyRegistry(get_settings().county)


@lru_cache(maxsize=1)
def default_projector() -> Projector:
    """For tools and tests that build an Incident without an app; the app wires its own (herald/api/app.py)."""
    return build_projector(get_settings(), default_counties())
