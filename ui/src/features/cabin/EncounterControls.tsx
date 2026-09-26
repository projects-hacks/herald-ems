import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useHerald } from "@/lib/store";
import { hhmm } from "@/lib/format";
import { useContract } from "@/lib/contract";

export function EncounterControls() {
  const s = useHerald((st) => st.snapshot);
  const disabled = useHerald((st) => st.source !== "live" || st.stale || st.conn !== "open");
  const setUi = useHerald((st) => st.setUi);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const contract = useContract();
  if (!s) return null;
  const inc = s.incident;
  const outcome = outcomeLabel(inc.disposition, contract);
  async function mark(action: "arrive" | "transfer") {
    setBusy(true); setError("");
    if (!await api.encounterAction(action)) setError("Could not record the time. Check the encounter and retry.");
    setBusy(false);
  }
  return <section className="encounter-card" aria-labelledby="care-transfer-heading">
    <h2 id="care-transfer-heading">Care transfer</h2>
    <p>Arrival, transfer of care and finishing this record are separate steps.</p>
    <dl className="encounter-times">
      <div><dt>Arrived at destination</dt><dd>{inc.arrived_at ? hhmm(inc.arrived_at) : "Not recorded"}</dd></div>
      <div><dt>Care transferred</dt><dd>{inc.transferred_at ? hhmm(inc.transferred_at) : "Not recorded"}</dd></div>
      {inc.ended_at && <div><dt>Encounter finished</dt><dd>{hhmm(inc.ended_at)}</dd></div>}
      {outcome && <div><dt>Outcome</dt><dd>{outcome}</dd></div>}
    </dl>
    {!inc.ended_at && <div className="cabin-actions">
      <button className="cabin-button" disabled={disabled || busy || !!inc.arrived_at || !!inc.transferred_at} onClick={() => void mark("arrive")}>Record arrival now</button>
      <button className="cabin-button" disabled={disabled || busy || !!inc.transferred_at} onClick={() => void mark("transfer")}>Record transfer of care now</button>
      <button className="cabin-button" disabled={disabled || busy} onClick={() => setUi({ confirmEndIncident: true })}>Finish this encounter…</button>
    </div>}
    <p>These buttons record the time you tap. ED delivery alone does not record transfer of care.</p>
    {error && <p role="alert">{error}</p>}
  </section>;
}

export function EncounterHistory() {
  const rows = useHerald((st) => st.snapshot?.encounter_history);
  const contract = useContract();
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
      {row.disposition && <span>{outcomeLabel(row.disposition, contract)}</span>}
      <span>{row.authorized ? `${row.destination} · ${row.delivery_pending ? "updates queued" : "confirmed record delivered"}` : "ED sharing was not authorized"}</span>
    </button>)}</div>
    {error && <p role="alert">{error}</p>}
    {selected && !error && <section className="retained-handoff" aria-label="Previous encounter handoff">
      <h3>Retained handoff · {selected.slice(-6)}</h3>
      {report?.id === selected ? <pre>{report.text}</pre> : <p role="status">Loading handoff…</p>}
    </section>}
  </section>;
}

/** How the encounter ended (config/dispositions.yaml). Required to finish: only "Transported by this unit" keeps a
 *  destination, an ETA and ED delivery; any other outcome tells an already-alerted ED the patient is not coming. */
export function OutcomeChoice({ value, onChange }: { value: string | null; onChange: (id: string) => void }) {
  const contract = useContract();
  const inc = useHerald((st) => st.snapshot?.incident);
  const outcomes = contract?.dispositions ?? [];
  const carried = !!(inc?.arrived_at || inc?.transferred_at);   // arrival or transfer recorded: it was a transport
  return <fieldset className="outcome-choice">
    <legend>How did this encounter end?</legend>
    {!outcomes.length && <p role="alert">The list of outcomes did not load. Reload the page.</p>}
    {outcomes.map((o) => {
      const off = carried && !o.transport;
      return <label key={o.id} className="outcome-option" data-disabled={off || undefined}>
        <input type="radio" name="outcome" value={o.id} checked={value === o.id} disabled={off} onChange={() => onChange(o.id)} />
        <span><b>{o.label}</b>{o.detail && <small>{o.detail}</small>}</span>
      </label>;
    })}
  </fieldset>;
}

export function outcomeLabel(id: string | null | undefined, contract: ReturnType<typeof useContract>): string | null {
  return id ? contract?.dispositions?.find((o) => o.id === id)?.label ?? id : null;
}
