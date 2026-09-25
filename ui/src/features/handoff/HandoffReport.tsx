import { useEffect, useState } from "react";
import { useHerald } from "@/lib/store";
import { Card, CardHeader } from "@/components/kit";
import { hhmm } from "@/lib/format";

interface Report {
  incident: { id: string }; as_of: string; text: string;
  format: { id: string; label: string; title: string }; formats: { id: string; label: string }[];
  sections: { id: string; label: string; lines: { text: string; status: string }[] }[];
  not_yet_known: { key: string; label: string }[]; not_yet_confirmed: { key: string; label: string }[];
}
export function HandoffReport() {
  const s = useHerald((state) => state.snapshot), source = useHerald((state) => state.source);
  const stale = useHerald((state) => state.stale || state.conn !== "open");
  const [report, setReport] = useState<Report | null>(null), [error, setError] = useState("");
  const [format, setFormat] = useState(""), [retry, setRetry] = useState(0);
  const patient = s?.incident.id, revision = JSON.stringify([s?.facts, s?.events, s?.county.id]);
  useEffect(() => { setFormat(""); }, [patient]);
  useEffect(() => {
    setReport(null); setError("");
    if (!patient || source === "fixture" || stale) return;
    const abort = new AbortController();
    let cancelled = false;
    const timer = setTimeout(() => abort.abort(), 5000);
    fetch(`/api/handoff${format ? `?format=${encodeURIComponent(format)}` : ""}`, { signal: abort.signal })
      .then(async (r) => { if (!r.ok) throw new Error("Report unavailable"); return r.json() as Promise<Report>; })
      .then((data) => { if (cancelled) return; if (data.incident.id === patient && useHerald.getState().snapshot?.incident.id === patient) setReport(data); else setError("Patient changed. Refresh the report."); })
      .catch(() => { if (!cancelled && useHerald.getState().snapshot?.incident.id === patient) setError("Could not load the handoff. Check the connection and retry."); })
      .finally(() => clearTimeout(timer));
    return () => { cancelled = true; clearTimeout(timer); abort.abort(); };
  }, [patient, revision, format, source, stale, retry]);
  const visible = report?.incident.id === patient && !stale && source !== "fixture" ? report : null;
  return <Card aria-label="Read-aloud handoff report" className="p-5">
    <CardHeader title="Read-aloud handoff" subtitle="Confirmed facts only · missing information stays explicit" />
    {source === "fixture" ? <p>This recording does not include a full handoff report.</p> : stale ? <p role="status">Report unavailable while the vehicle connection is stale.</p> : <>
      <label className="text-body">Format<select className="ml-3 min-h-12 rounded-lg border border-border-control bg-surface-2 px-3" value={format} onChange={(e) => setFormat(e.target.value)}><option value="">Automatic</option>{(visible?.formats ?? report?.formats ?? []).map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select></label>
      {error ? <p role="alert">{error} <button className="min-h-12 px-3 text-herald-accent" onClick={() => setRetry((n) => n + 1)}>Retry</button></p> : !visible ? <p role="status">Loading report…</p> : <>
        <h3 className="mt-4 text-title font-semibold">{visible.format.title}</h3>
        <p className="text-meta text-text-muted">As of {hhmm(visible.as_of)}</p>
        <div className="mt-4 space-y-5">{visible.sections.map((section) => <section key={section.id}><h4 className="text-title font-semibold">{section.label}</h4><ul className="space-y-3 text-critical leading-relaxed">{section.lines.map((line, i) => <li key={i} className={line.status === "missing" ? "text-text-muted" : ""}>{line.text}</li>)}</ul></section>)}</div>
        {visible.not_yet_known.length > 0 && <p className="mt-4 text-body">Not yet known: {visible.not_yet_known.map((f) => f.label).join(" · ")}</p>}
        {visible.not_yet_confirmed.length > 0 && <p className="mt-3 text-body text-medium-fg">Not yet confirmed (not in report): {visible.not_yet_confirmed.map((f) => f.label).join(" · ")}</p>}
      </>}
    </>}
  </Card>;
}
