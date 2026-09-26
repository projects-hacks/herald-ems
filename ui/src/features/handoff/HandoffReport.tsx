// The written handoff report, as the receiving team hears it: the server's report (GET /api/handoff, confirmed facts
// only, MIST for trauma and SBAR for medical calls), large enough to read aloud from arm's length, one row per line.
// Beside it, the latest confirmed vitals as tiles and who told us what. A recorded replay has no server, so it shows a
// summary built from the recorded snapshot instead; never both.
import { useCallback, useEffect, useState } from "react";
import { CircleDashed, HeartPulse, Users } from "lucide-react";
import { Badge, Card, CardHeader, SEVERITY, SeverityBadge, TEXT } from "@/components/kit";
import { label, useContract } from "@/lib/contract";
import { hhmm, sourceName } from "@/lib/format";
import { useHerald } from "@/lib/store";
import type { HandoffInformant, HandoffLine, HandoffReportData, Role, Snapshot } from "@/lib/types";
import { cn } from "@/lib/utils";
import { cardSeverity, shownValue, vitalCards } from "@/pages/TrendsPage";
import { reportInformants } from "./informants";
import { snapshotReport } from "./snapshotReport";

export interface HandoffReportState {
  report: HandoffReportData | null;
  error: string; replay: boolean; stale: boolean;
  format: string; setFormat: (id: string) => void; retry: () => void;
  /** A report the server returned from an action (not obtained), shown at once instead of waiting for a refetch. */
  accept: (r: HandoffReportData) => void;
}

export function useHandoffReport(): HandoffReportState {
  const s = useHerald((state) => state.snapshot), source = useHerald((state) => state.source);
  const stale = useHerald((state) => state.stale || state.conn !== "open");
  const [report, setReport] = useState<HandoffReportData | null>(null), [error, setError] = useState("");
  const [format, setFormat] = useState(""), [attempt, setAttempt] = useState(0);
  const patient = s?.incident.id, revision = JSON.stringify([s?.facts, s?.events, s?.county.id, s?.incident]);
  const replay = source === "fixture";
  useEffect(() => { setFormat(""); setReport(null); }, [patient]);
  useEffect(() => {
    setError("");
    if (!patient || replay || stale) return;
    const abort = new AbortController();
    let cancelled = false;
    const timer = setTimeout(() => abort.abort(), 5000);
    // The previous report stays on screen while the next one loads, so a new fact does not blank the page.
    fetch(`/api/handoff${format ? `?format=${encodeURIComponent(format)}` : ""}`, { signal: abort.signal })
      .then(async (r) => { if (!r.ok) throw new Error("Report unavailable"); return r.json() as Promise<HandoffReportData>; })
      .then((data) => { if (cancelled) return; if (data.incident.id === patient && useHerald.getState().snapshot?.incident.id === patient) setReport(data); else setError("Patient changed. Refresh the report."); })
      .catch(() => { if (!cancelled && useHerald.getState().snapshot?.incident.id === patient) setError("Could not load the handoff. Check the connection and retry."); })
      .finally(() => clearTimeout(timer));
    return () => { cancelled = true; clearTimeout(timer); abort.abort(); };
  }, [patient, revision, format, replay, stale, attempt]);
  const accept = useCallback((r: HandoffReportData) => {
    if (r.incident?.id === useHerald.getState().snapshot?.incident.id) setReport(r);
  }, []);
  const visible = replay ? (s ? snapshotReport(s) : null) : report?.incident.id === patient && !stale ? report : null;
  return { report: visible, error, replay, stale, format, setFormat, retry: () => setAttempt((n) => n + 1), accept };
}

/** "Chief complaint: suspected stroke" -> ["Chief complaint", "suspected stroke"], so the value stands out on its row;
 *  a line that is a sentence of its own ("68-year-old female", "BP 182/104 mmHg") stays whole. */
export function splitLine(text: string): [string | null, string] {
  const i = text.indexOf(": ");
  return i > 0 && i <= 40 ? [text.slice(0, i), text.slice(i + 2)] : [null, text];
}

/** Who gave a line and when, for its hover title: the time never sits inline in the value. */
function lineOrigin(line: HandoffLine): string | undefined {
  const parts = (line.sources ?? []).map((src) => {
    const when = src.ts ? hhmm(src.ts) : src.time ?? "";
    return [sourceName({ role: src.role as Role, speaker: src.speaker }), when].filter(Boolean).join(" ");
  });
  return parts.length ? [...new Set(parts)].join(", ") : undefined;
}

function ReportLine({ line }: { line: HandoffLine }) {
  const [name, value] = splitLine(line.text);
  const settled = line.status === "not_obtained";
  return <li data-status={line.status} title={lineOrigin(line)}
    className={cn("report-line", line.status !== "confirmed" && "text-text-muted")}>
    {line.status !== "confirmed" && <CircleDashed size={16} aria-hidden className="report-line-icon" />}
    {name === null ? line.text : <><span className="report-line-label">{name}:</span>{" "}
      {settled ? null : <span className="report-line-value">{value}</span>}</>}
    {settled && <Badge tone="neutral" className="ml-2 align-middle">unable to obtain</Badge>}
  </li>;
}

/** The latest confirmed vitals as tiles: a label, the value large, its unit; the reading's time on hover. */
function VitalTiles({ s }: { s: Snapshot | null }) {
  const cards = s ? vitalCards(s).filter((card) => card.latest) : [];
  return <Card aria-labelledby="report-vitals-h" className="report-side-card">
    <CardHeader icon={HeartPulse} cat="heart" title="Latest vitals" id="report-vitals-h" subtitle="Confirmed readings only" />
    {cards.length ? <ul className="report-vitals">
      {cards.map((card) => {
        const v = shownValue(card), sev = cardSeverity(card);
        return <li key={card.key} data-vital={card.key} title={`Recorded ${hhmm(card.latest!.ts)}`}
          aria-label={`${card.label}: ${v.value}${v.unit ? ` ${v.unit}` : ""}${sev ? `, ${SEVERITY[sev].word}` : ""}`}>
          <span className="report-vital-label">{card.label}</span>
          <span className="report-vital-value"><span className={cn("rounded-num text-kpi", sev && TEXT[SEVERITY[sev].tone])}>{v.value}</span>
            {v.unit && <span className="report-vital-unit">{v.unit}</span>}</span>
          {sev && <SeverityBadge severity={sev} className="self-start" />}
          {v.detail && <span className="report-vital-detail">{v.detail}</span>}
        </li>;
      })}
    </ul> : <p className="report-side-empty">No confirmed vitals yet.</p>}
  </Card>;
}

/** A confirmed line that only reads out vitals the tiles beside the report already show: left out of the rows, so
 *  each reading appears once on screen (the spoken and exported report still reads them). */
function inVitalTiles(line: HandoffLine, s: Snapshot | null): boolean {
  const keys = line.keys ?? [];
  return !!s && line.status === "confirmed" && keys.length > 0
    && keys.every((k) => k.startsWith("vitals.") && s.facts[k]?.status === "confirmed");
}

/** Who told us what: each source and what they gave, people other than the crew first. */
export function WhoToldUs({ rows }: { rows: HandoffInformant[] }) {
  return <Card aria-labelledby="report-who-h" className="report-side-card">
    <CardHeader icon={Users} cat="speech" title="Who told us what" id="report-who-h" subtitle="Where each confirmed fact came from" />
    {rows.length ? <ul className="report-who">
      {rows.map((row) => <li key={`${row.role}:${row.who}`} data-role={row.role}>
        <span className="report-who-name">{row.who.charAt(0).toUpperCase() + row.who.slice(1)}</span>
        <span className="report-who-items">{row.items.join(", ")}</span>
      </li>)}
    </ul> : <p className="report-side-empty">No confirmed facts yet.</p>}
  </Card>;
}

/** The report: its sections on the left, one row per line; the latest vitals and who told us what on the right (below
 *  it on a narrow screen). `h` comes from useHandoffReport(), shared with the leftovers and the export on the page. */
export function HandoffReportView({ h }: { h: HandoffReportState }) {
  const r = h.report;
  const s = useHerald((st) => st.snapshot);
  const c = useContract();
  if (!r) return <Card aria-label="Handoff report" className="handoff-report">
    <div className="handoff-report-state">
      {h.stale && !h.replay ? <p role="status">Report unavailable while the vehicle connection is stale.</p>
        : h.error ? <p role="alert">{h.error} <button type="button" className="report-link" onClick={h.retry}>Retry</button></p>
        : <p role="status">Loading report…</p>}
    </div>
  </Card>;
  return <div className="handoff-layout">
    <Card aria-label="Handoff report" className="handoff-report">
      <header className="handoff-report-head">
        <div className="min-w-0">
          <h2>{r.format.title}</h2>
          <p><span className="num">{h.replay ? "Recorded scenario · as of" : "As of"} {hhmm(r.as_of)}</span> · confirmed facts only</p>
        </div>
        {r.formats.length > 1 && <div className="report-formats" role="group" aria-label="Report format">
          <span>Report as:</span>
          {r.formats.map((f, i) => <span key={f.id} className="contents">
            {i > 0 && <span aria-hidden>/</span>}
            <button type="button" className="report-link" aria-pressed={r.format.id === f.id}
              onClick={() => { if (r.format.id !== f.id) h.setFormat(f.id); }}>{f.label}</button>
          </span>)}
        </div>}
      </header>
      <div className="handoff-report-body">
        {r.sections.map((section) => ({ section, lines: section.lines.filter((line) => !inVitalTiles(line, s)) }))
          .filter(({ lines }) => lines.length)
          .map(({ section, lines }) => <section key={section.id} aria-labelledby={`report-${section.id}`} className="report-section">
            <h3 id={`report-${section.id}`} className="label-caps">{section.label}</h3>
            <ul>{lines.map((line, i) => <ReportLine key={i} line={line} />)}</ul>
          </section>)}
      </div>
    </Card>
    <aside className="handoff-aside" aria-label="Vitals and sources">
      <VitalTiles s={s} />
      <WhoToldUs rows={reportInformants(r, (key) => label(c, key))} />
    </aside>
  </div>;
}

/** The report on its own, loading itself (for screens that show only the report). */
export function HandoffReport() {
  return <HandoffReportView h={useHandoffReport()} />;
}

/** Saves the report text as a file: the quiet "Export" on the hand over bar. */
export function downloadReport(r: HandoffReportData) {
  const url = URL.createObjectURL(new Blob([r.text], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url; link.download = `herald-${r.incident.id}-handoff.txt`;
  link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
