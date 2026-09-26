"""The written handoff report: the incident projected into a radio/bedside report (MIST for trauma, SBAR for medical
calls) from confirmed facts and the scores, checklists and alerts the Projector already computed.

No model writes any of it. Every line is a template from config/handoff.yaml filled with confirmed values, and
carries the ids, speaker and time of the facts behind it. Facts waiting for the medic's tap are listed by name only;
required items with no confirmed value read "not yet known", or "unable to obtain" once the medic marked them so
(AGENTS.md invariants 3, 4, 5, 6). A section with nothing to say is left out.
"""
from __future__ import annotations

from typing import Optional
from zoneinfo import ZoneInfo

from ..checklists.items import ChecklistItem
from ..core import not_obtained as unobtainable
from ..core.trends import TrendRules
from ..core.vocabulary import Vocabulary
from .config import HandoffConfig
from .kinds import LINE_KINDS
from .lines import BuildContext, Line
from .text import render_text
from .view import ConfirmedView


class HandoffBuilder:
    def __init__(self, config: HandoffConfig, vocabulary: Vocabulary, scales, tz: ZoneInfo,
                 unit_id: Optional[str] = None, kinds: Optional[dict] = None, trends: Optional[TrendRules] = None):
        self.cfg, self.vocab, self.scales, self.tz = config, vocabulary, scales, tz
        self.unit_id, self.kinds = unit_id, kinds or LINE_KINDS
        self.trends = trends if trends is not None else TrendRules.from_config()

    def formats(self) -> list[dict]:
        return [{"id": fid, "label": f["label"]} for fid, f in self.cfg.formats.items()]

    def select(self, open_checklists: list[str]) -> tuple[str, str]:
        """(format id, why): the first `select` rule with an open checklist, else the default."""
        for rule in self.cfg.select:
            hit = next((c for c in rule.get("checklists", []) if c in open_checklists), None)
            if hit:
                return rule["format"], f"checklist:{hit}"
        return self.cfg.default, "default"

    # ---------- the report ----------
    def build(self, incident, format_id: Optional[str] = None, snapshot: Optional[dict] = None) -> dict:
        if format_id is not None and format_id not in self.cfg.formats:
            raise KeyError(format_id)
        with incident.lock:
            snap = snapshot if snapshot is not None else incident.snapshot()
            open_ids = [r["id"] for r in snap["readiness"]]
            fid, why = (format_id, "request") if format_id else self.select(open_ids)
            fmt = self.cfg.formats[fid]
            view = ConfirmedView(incident, self.vocab, self.cfg, self.tz, {"unit": self.unit_id})
            ctx = BuildContext(view, snap, self.scales, self.cfg, set(open_ids), self.trends)
            sections, built = [], []
            for sec in fmt["sections"]:
                lines = self._section_lines(sec, ctx)
                built += lines
                if lines:                 # a section with nothing to say is not read
                    sections.append({"id": sec["id"], "label": sec["label"],
                                     "say_label": sec.get("say_label", True), "source": sec.get("source"),
                                     "lines": [self._line(ln, view) for ln in lines]})
            covered = {k for ln in built for k in ln.keys} | ctx.covered
            gaps, gap_labels = self._gaps(snap["readiness"], covered, view.not_obtained)
            last = incident.facts[-1].ts if incident.facts else incident.started
            report = {
                "format": {k: fmt[k] for k in ("id", "label", "title", "source")},
                "formats": self.formats(),
                "selected_by": why,
                "incident": snap["incident"],
                "county": snap["county"],
                "as_of": last.isoformat(),
                "open_checklists": open_ids,
                "sections": sections,
                "not_yet_known": gaps,
                "not_obtained": self._not_obtained(view, built, gap_labels),
                "not_yet_confirmed": view.unconfirmed(),
            }
        report["text"] = render_text(report, self.cfg.words)
        return report

    def _section_lines(self, sec: dict, ctx: BuildContext) -> list[Line]:
        lines: list[Line] = []
        for spec in sec["lines"]:
            gate = spec.get("when_checklists")
            if gate and not ctx.open_checklists & set(gate):
                continue
            lines.extend(self.kinds[spec["kind"]].build(spec, ctx))
        if not lines and sec.get("empty"):
            lines.append(Line("empty", sec["empty"], status="empty"))
        return lines

    @staticmethod
    def _line(ln: Line, view: ConfirmedView) -> dict:
        row = {"kind": ln.kind, "status": ln.status, "text": ln.text, "keys": list(ln.keys),
               "fact_ids": [f.id for f in ln.facts], "sources": [view.source(f) for f in ln.facts]}
        if ln.source:
            row["source"] = ln.source
        if ln.criterion:
            row["criterion"] = ln.criterion
        return row

    def _gaps(self, readiness: list[dict], covered: set[str], not_obtained: set[str]) -> tuple[list[dict], dict]:
        """Open checklists' missing items that no report line covers, each once, in checklist order, and the labels
        of the ones the medic marked "unable to obtain" (listed apart, not here). A record item (e.g. the time of
        aspirin) is never listed: the treatment list is the record of what was given, and a report must never read
        as a prompt to give something (AGENTS.md invariant 3)."""
        out: dict[str, dict] = {}
        marked: dict[str, str] = {}
        for r in readiness:
            for item in r["items"]:
                if item["state"] != "missing":
                    continue
                refs = ChecklistItem.parse({"key": item["key"], "label": item["label"]}).refs
                if any(x.kind == "record" or (f"@{x.key}" if x.kind == "score" else x.key) in covered for x in refs):
                    continue
                vocab_keys = [x.key for x in refs if x.kind == "key"]
                if unobtainable.covers(not_obtained, vocab_keys):
                    for k in vocab_keys:
                        marked.setdefault(k, item["label"])
                    continue
                row = out.setdefault(item["key"], {"key": item["key"], "label": item["label"], "checklists": [],
                                                   "text": f"{item['label']} ({item['note']})" if item.get("note")
                                                   else item["label"]})
                if item.get("note"):
                    row["note"] = item["note"]
                row["checklists"].append(r["id"])
        return list(out.values()), marked

    def _not_obtained(self, view: ConfirmedView, lines: list[Line], gap_labels: dict[str, str]) -> list[dict]:
        """Every mark still in force, in the order made: its label (the report line's, else the checklist item's,
        else the vocabulary's) and whether a report line already says "unable to obtain" for it (`inline`), so the
        read-aloud text says it once."""
        inline = {k: ln.label for ln in lines if ln.status == "not_obtained" for k in ln.keys}
        out = []
        for mark in view.not_obtained_marks:
            parts = unobtainable.alternatives(mark)
            label = next((inline[p] for p in parts if p in inline), None) \
                or next((gap_labels[p] for p in parts if p in gap_labels), None) or self.vocab.label(parts[0])
            out.append({"key": mark, "label": label, "inline": any(p in inline for p in parts)})
        return out

    @staticmethod
    def summary(report: dict) -> dict:
        """The compact form carried in the snapshot (`handoff`)."""
        lines = [ln for s in report["sections"] for ln in s["lines"]]
        return {"format": report["format"]["id"], "label": report["format"]["label"],
                "selected_by": report["selected_by"],
                "lines": sum(ln["status"] == "confirmed" for ln in lines),
                "missing": sum(ln["status"] == "missing" for ln in lines) + len(report["not_yet_known"]),
                "unconfirmed": len(report["not_yet_confirmed"])}
