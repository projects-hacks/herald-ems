// Previous encounters on this vehicle, read-only. Arrival, transfer of care and finishing are one step now: Hand over
// on the handoff (features/handoff/HandoverBar.tsx).
import { useEffect, useState } from "react";
import { useHerald } from "@/lib/store";
import { hhmm } from "@/lib/format";

export function EncounterHistory() {
  const rows = useHerald((st) => st.snapshot?.encounter_history);
  const persisted = useHerald((st) => st.snapshot?.history_persisted);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<{ id: string; text: string } | null>(null), [error, setError] = useState("");
  useEffect(() => {
    setReport(null); setError("");
    if (!selected) return;
    const abort = new AbortController();
    fetch(`/api/encounters/${encodeURIComponent(selected)}`, { signal: abort.signal })
      .then(async (r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((r) => { if (!abort.signal.aborted) setReport({ id: r.incident.id, text: r.handoff.text }); })
      .catch(() => { if (!abort.signal.aborted) setError("Could not load this retained handoff. Select it again to retry."); });
    return () => abort.abort();
  }, [selected]);
  return <section className="encounter-card" aria-labelledby="retained-heading">
    <h2 id="retained-heading">Previous encounters</h2>
    <p>{persisted ? "Encrypted records on this vehicle. Opening a handoff does not switch the active patient." : "Local recovery is off. Records last only until the server restarts."}</p>
    {!rows?.length && <p>No previous encounters in this vehicle’s history.</p>}
    <div className="encounter-history">{rows?.map((row) => <button className="encounter-history-row" key={row.id} onClick={() => setSelected(selected === row.id ? null : row.id)} aria-expanded={selected === row.id}>
      <strong>{row.label} · {row.id.slice(-6)}</strong><span>{`${new Date(row.started).toLocaleDateString()} ${hhmm(row.started)}`} · {row.summary}</span>
      <span>{row.authorized ? `${row.destination} · ${row.delivery_pending ? "updates queued" : "confirmed record delivered"}` : "ED sharing was not authorized"}</span>
    </button>)}</div>
    {error && <p role="alert">{error}</p>}
    {selected && !error && <section className="retained-handoff" aria-label="Previous encounter handoff">
      <h3>Retained handoff · {selected.slice(-6)}</h3>
      {report?.id === selected ? <pre>{report.text}</pre> : <p role="status">Loading handoff…</p>}
    </section>}
  </section>;
}
