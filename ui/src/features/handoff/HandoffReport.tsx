// The written handoff report, as the receiving team hears it: the server's report (GET /api/handoff, confirmed facts
// only, MIST for trauma and SBAR for medical calls), large enough to read aloud from arm's length. A recorded replay
// has no server, so it shows a summary built from the recorded snapshot instead; never both.
import { useCallback, useEffect, useState } from "react";
import { Badge, Card } from "@/components/kit";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import type { HandoffReportData } from "@/lib/types";
import { cn } from "@/lib/utils";
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

/** The report card. `h` comes from useHandoffReport(), shared with the leftovers and the export on the same page. */
export function HandoffReportView({ h }: { h: HandoffReportState }) {
  const r = h.report;
  return <Card aria-label="Handoff report" className="handoff-report">
    {!r ? <div className="handoff-report-state">
      {h.stale && !h.replay ? <p role="status">Report unavailable while the vehicle connection is stale.</p>
        : h.error ? <p role="alert">{h.error} <button type="button" className="report-link" onClick={h.retry}>Retry</button></p>
        : <p role="status">Loading report…</p>}
    </div> : <>
      <header className="handoff-report-head">
        <div className="min-w-0">
          <h2>{r.format.title}</h2>
          <p>{h.replay ? "Recorded scenario · confirmed facts only" : `As of ${hhmm(r.as_of)} · confirmed facts only`}</p>
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
        {r.sections.map((section) => <section key={section.id} aria-labelledby={`report-${section.id}`}>
          <h3 id={`report-${section.id}`} className="label-caps">{section.label}</h3>
          <ul>{section.lines.map((line, i) => <li key={i} data-status={line.status}
            className={cn(line.status !== "confirmed" && "text-text-muted")}>
            {line.text}
            {line.status === "not_obtained" && <Badge tone="neutral" className="ml-2 align-middle">unable to obtain</Badge>}
          </li>)}</ul>
        </section>)}
      </div>
    </>}
  </Card>;
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
