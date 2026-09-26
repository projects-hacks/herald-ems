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
from .corroboration import BatchConfirmation, CorroborationRules
from .schema import Fact, Status, utcnow
from .trends import TrendRules
from .vital_severity import VitalRanges
from .vocabulary import Vocabulary, default_vocabulary, norm_value

SCORE_HISTORY = "news2"          # the score whose history drives the "rose" alert


class Projector:
    def __init__(self, vocabulary: Vocabulary, scales: ScaleRegistry, checklists: ChecklistEngine,
                 counties: CountyRegistry, trends: TrendRules, tz: ZoneInfo, reassess_min: Optional[int] = None,
                 batch: Optional[BatchConfirmation] = None, vital_ranges: Optional[VitalRanges] = None):
        self.vocab, self.scales, self.checklists = vocabulary, scales, checklists
        self.counties, self.trends, self.tz, self.reassess_override = counties, trends, tz, reassess_min
        self.batch = batch or BatchConfirmation(vocabulary, CorroborationRules.from_config())
        # Absolute clinical severity per vital value (config/vital_ranges.yaml). Empty ranges = no severity ever, so
        # an older config or a test that omits it degrades to the previous "no colour" behaviour rather than failing.
        self.vital_ranges = vital_ranges or VitalRanges({})

    # ---------- score history (called on commit) ----------
    def record_scores(self, inc) -> None:
        n = self.scales[SCORE_HISTORY].evaluate(inc.values(confirmed_only=True))
        last = inc.news2_history[-1] if inc.news2_history else None
        if last is None or (last["score"], last["complete"]) != (n["score"], n["complete"]):
            inc.news2_history.append({"ts": utcnow().isoformat(), "score": n["score"],
                                      "complete": n["complete"], "band": n["band"]})

    def fact_view(self, f: Fact, vitals_applicable: bool = True, spo2_scale: int = 1) -> dict:
        d = f.model_dump(mode="json")
        d["label"] = self.vocab.label(f.key)
        d["unit"] = f.unit or self.vocab.meta(f.key).get("unit")
        # Absolute clinical severity of this value, so the screen can colour an abnormal-but-steady reading, not only
        # a changing one (config/vital_ranges.yaml). None for everything that has no coloured band (non-vitals,
        # diastolic BP, mid-range values); the field is only added when there is a severity to show, so the snapshot
        # shape for non-vitals is unchanged. `vitals_applicable` withdraws the colouring for the patients the adult
        # NEWS2 chart is not valid for (paediatric, documented pregnancy) -- see VitalRanges.severity.
        severity = self.vital_ranges.severity(f.key, f.value, applicable=vitals_applicable, spo2_scale=spo2_scale)
        if severity:
            d["severity"] = severity
        return d

    def _vitals_applicable(self, results: dict) -> bool:
        """Whether the adult NEWS2-derived severity colouring applies to this patient. It withdraws for exactly the
        patients NEWS2 itself withdraws for: `excluded` means paediatric or documented pregnancy (config/scores/
        news2.yaml applicability). `incomplete` (age not yet known) still colours, because before an age is spoken
        the working assumption on an EMS call is an adult and an out-of-range value is worth flagging; the moment a
        paediatric age arrives the colouring withdraws."""
        return results.get("news2", {}).get("applicability") != "excluded"

    # ---------- the picture ----------
    def snapshot(self, inc) -> dict:
        with inc.lock:
            now = utcnow()
            county = self.counties.active
            vals, all_vals = inc.values(confirmed_only=True), inc.values(confirmed_only=False)
            results = self.scales.evaluate_all(vals, county["id"])          # published + this county's criteria
            results_all = self.scales.evaluate_all(all_vals, county["id"])  # as if every waiting fact were confirmed
            complaint = all_vals.get("complaint.chief")
            started = {s.id for s in self.scales.item_scales() if any(k.startswith(s.key_prefix) for k in all_vals)}
            alert_ids = self.checklists.active(inc.dispatch, complaint, all_vals, results_all)
            readiness, items = self._readiness(alert_ids, vals, all_vals, results, results_all, started)
            missing, unknown = self._needs_attention(readiness, items, alert_ids, vals, all_vals, results)
            vitals_applicable = self._vitals_applicable(results_all)
            # NEWS2 SpO2 scale: 2 only when the medic has CONFIRMED it (RCP: Scale 2 under clinician direction only;
            # patient.spo2_scale is require_tap). Anything else, including an unconfirmed proposal, is Scale 1.
            spo2_scale = 2 if vals.get("patient.spo2_scale") == 2 else 1
            changed = self._trends(inc, vitals_applicable, spo2_scale)
            alerts = self._alerts(inc, changed, results, county, vals)
            summary = " ".join([str(all_vals["patient.age"])] if "patient.age" in all_vals else [])
            if "patient.sex" in all_vals:
                summary = f"{summary} {str(all_vals['patient.sex']).upper()[:1]}".strip()
            latest = {f.key: self.fact_view(f, vitals_applicable, spo2_scale) for f in inc.facts if f.status != Status.rejected}
            # event keys (vocabulary merge "each": a dose given, a procedure) keep every event, in order; `facts`
            # still holds the latest one per key for screens that show one value
            events = {k: [self.fact_view(f) for f in inc.facts if f.key == k and f.status != Status.rejected]
                      for k, m in self.vocab.keys.items() if m.get("merge") == "each"}
            return {
                "incident": {"id": inc.id, "dispatch": inc.dispatch, "started": inc.started.isoformat(),
                             "ended_at": inc.ended_at.isoformat() if inc.ended_at else None,
                             "arrived_at": inc.arrived_at.isoformat() if inc.arrived_at else None,
                             "transferred_at": inc.transferred_at.isoformat() if inc.transferred_at else None,
                             "media_disposal": inc.media_disposal},
                "summary": summary + (f" · {complaint}" if complaint else ""),
                "readiness": readiness,
                "needs_attention": {"missing": missing, "unknown": unknown},
                "changed": changed,
                # One capture's unconfirmed readings, split into the set the medic can take in one action and the
                # ones that need looking at (herald/core/corroboration.py, config/corroboration.yaml).
                "capture_groups": self.batch.groups(inc),
                "scores": {**results, "news2_history": inc.news2_history,
                           "stroke_scales": county["stroke"]["scales"],
                           "primary_stroke_scale": county["stroke"]["primary_scale"]},
                "county": {"id": county["id"], "name": county["name"]},
                "alerts": alerts,
                "clocks": self._clocks(inc, now, county),
                "facts": latest,
                "events": {k: v for k, v in events.items() if v},
                "timeline": [self.fact_view(f) for f in inc.facts[-60:]],
                "audit": inc.audit_log[-60:],
                "transcripts": inc.transcripts[-20:],
                "ed_sync": inc.ed_sync,
                "counters": {"facts": len(inc.facts), "cloud_ai_calls": 0},
            }

    def _readiness(self, alert_ids, vals, all_vals, results, results_all, started):
        """One entry per open checklist; also returns the parsed items by key (for needs_attention)."""
        out, parsed = [], {}
        for aid in alert_ids:
            rows = []
            for item in self.checklists.items(aid):
                if not item.listed(vals):
                    continue
                parsed[item.key] = item
                state = item.state(vals, all_vals, results, results_all, started)
                row = {"key": item.key, "label": item.label, "state": state}
                if item.note and state != "done":
                    row["note"] = item.note
                rows.append(row)
            done = sum(i["state"] == "done" for i in rows)
            out.append({"id": aid, "label": self.checklists.label(aid), "source": self.checklists.source(aid),
                        "done": done, "total": len(rows), "ready": done == len(rows), "items": rows})
        return out, parsed

    def _needs_attention(self, readiness, items, alert_ids, vals, all_vals, results):
        missing, unknown, seen = [], [], set()

        def add(key: str, label: str, pending: bool, note=None, kind_key=None):
            if key in seen or key in vals:
                return
            seen.add(key)
            kind = self.vocab.meta(kind_key).get("kind", "measure") if kind_key else "measure"
            entry = {"key": key, "label": label, "pending_confirm": pending}
            if note:
                entry["note"] = note
            (unknown if kind == "history" else missing).append(entry)

        for r in readiness:
            for i in r["items"]:
                if i["state"] != "done":
                    keys = items[i["key"]].vocab_keys
                    add(i["key"], i["label"], i["state"] == "pending", i.get("note"), keys[0] if keys else None)
        news2 = self.scales["news2"]
        for label in results["news2"]["missing"]:
            key = next(p["key"] for p in news2.parameters if p["label"] == label)
            add(key, f"{self.vocab.label(key)} (for NEWS2)", key in all_vals, kind_key=key)
        for key in results["news2"].get("applicability_missing", []):
            add(key, f"{self.vocab.label(key)} (for NEWS2 applicability)", key in all_vals, kind_key=key)
        seeds = self.checklists.default_unknowns + [u for aid in alert_ids for u in self.checklists.unknowns(aid)]
        for key in seeds:
            add(key, self.vocab.label(key), key in all_vals, kind_key=key)
        return missing, unknown

    def _trend_points(self, inc, key: str) -> list[Fact]:
        """The readings a trend may be built from: confirmed facts, plus unconfirmed readings from the sources
        config/trends.yaml lists (the camera watching the monitor, a monitor feed). An unconfirmed reading can raise
        an alert in the cabin; it still cannot leave the vehicle, because the relay and the report ask the incident
        for confirmed facts only."""
        return [f for f in inc.history(key)
                if f.status == Status.confirmed or self.trends.counts_unconfirmed(f.captured_by.value)]

    def _trends(self, inc, vitals_applicable: bool = True, spo2_scale: int = 1) -> list[dict]:
        changed = []
        for key in self.trends.keys():
            h = self._trend_points(inc, key)
            if len(h) >= 2:
                series = [f.value for f in h]
                waiting = [f for f in h if f.status != Status.confirmed]
                direction = "up" if series[-1] > series[-2] else ("down" if series[-1] < series[-2] else "flat")
                latest_severity = self.vital_ranges.severity(key, series[-1], applicable=vitals_applicable,
                                                             spo2_scale=spo2_scale)
                row = {"key": key, "label": self.vocab.label(key), "series": series,
                       "times": [(f.provenance.observed_at or f.ts).isoformat() for f in h], "delta": series[-1] - series[0],
                       "direction": direction,
                       "significant": self.trends.significant(key, series[-2], series[-1]),
                       # Absolute severity of the latest reading, so the trend tile colours a value that is dangerous
                       # even when it has not moved enough to be `significant` (config/vital_ranges.yaml).
                       **({"severity": latest_severity} if latest_severity else {}),
                       # The smallest change worth noticing (config/trends.yaml), so a sparkline can keep a minimum
                       # visible span and a sub-threshold wobble does not look like a cliff. Display hint only.
                       **({"floor": self.trends.floor(key)} if self.trends.floor(key) is not None else {}),
                       # Labelled for the screen: which of these readings still need the medic's tap, per point too,
                       # so a screen can draw the confirmed trend and hold a waiting camera reading apart from it.
                       "unconfirmed": bool(waiting), "unconfirmed_fact_ids": [f.id for f in waiting],
                       "confirmed": [f.status == Status.confirmed for f in h]}
                if waiting:
                    newest = waiting[-1]
                    message = self.trends.sentence(
                        newest.captured_by.value, label=row["label"], value=series[-1], previous=series[-2],
                        direction=direction, delta=abs(series[-1] - series[-2]),
                        unit=self.vocab.meta(key).get("unit"))
                    if message:
                        row["message"] = message
                changed.append(row)
        return changed

    def _alerts(self, inc, changed, results, county, vals) -> list[dict]:
        alerts = []
        for key in sorted(self.vocab.contradiction_keys):
            h = inc.history(key)
            if len(h) >= 2 and norm_value(h[-1].value) != norm_value(h[-2].value) and h[-1].status == Status.unconfirmed:
                alerts.append({"type": "contradiction", "key": key, "label": self.vocab.label(key),
                               "confirm_fact_id": h[-1].id, "facts": [self.fact_view(f) for f in h[-2:]]})
        for c in changed:
            if c["significant"]:
                alert = {"type": "significant_change", "key": c["key"], "label": c["label"], "series": c["series"],
                         "unconfirmed": c["unconfirmed"], "unconfirmed_fact_ids": c["unconfirmed_fact_ids"]}
                if "message" in c:       # the wording is content (config/trends.yaml), never a literal here
                    alert["message"] = c["message"]
                alerts.append(alert)
        hist = [x for x in inc.news2_history if x["complete"]]
        if hist and hist[-1]["band"] == "high" and not any(x["band"] == "high" for x in hist[:-1]):
            alerts.append({"type": "news2_high", "label": "NEWS2", "score": hist[-1]["score"],
                           "band": "high"})
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
        for sid, r in results.items():                 # a county's criteria met (Trauma Alert, sepsis pre-notification)
            alert_type = self.scales[sid].d.get("alert_type")
            if r.get("kind") != "criteria" or not alert_type or not r["met"]:
                continue
            alert = {"type": alert_type, "score": sid, "label": r["name"], "level": r["level"],
                     "criteria": [t for g in self.scales[sid].groups if g.get("met") for t in r[g["id"]]]}
            rules = self.checklists.county_rules(sid, vals)
            if rules:
                alert.update(county_rule=rules, county=county["name"])
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
    from ..config import load_yaml
    vocab = default_vocabulary()
    return Projector(vocab, default_scales(), ChecklistEngine.from_config(counties), counties,
                     TrendRules.from_config(), ZoneInfo(settings.timezone), settings.reassess_min,
                     BatchConfirmation(vocab, CorroborationRules.from_config()),
                     VitalRanges.from_config(load_yaml))


@lru_cache(maxsize=1)
def default_counties() -> CountyRegistry:
    return CountyRegistry(get_settings().county)


@lru_cache(maxsize=1)
def default_projector() -> Projector:
    """For tools and tests that build an Incident without an app; the app wires its own (herald/api/app.py)."""
    return build_projector(get_settings(), default_counties())
