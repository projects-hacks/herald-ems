import { useState } from "react";
import { useHerald } from "@/lib/store";
import { api } from "@/lib/api";
import { PatientStrip } from "./PatientStrip";
import { Button } from "./kit";

export function PatientRoster({ expanded = false }: { expanded?: boolean }) {
  const s = useHerald((state) => state.snapshot);
  const setUi = useHerald((state) => state.setUi);
  const disabled = useHerald((state) => state.source === "fixture" || state.stale || state.conn !== "open");
  const [busy, setBusy] = useState(false), [label, setLabel] = useState("");
  async function perform(action: () => Promise<boolean>) {
    if (busy || disabled) return;
    setBusy(true);
    try { if (!await action()) useHerald.getState().showToast("Patient action failed. Check the active patient before continuing."); else setLabel(""); }
    finally { setBusy(false); }
  }
  if (!s) return null;
  const anotherOpen = (s.patients ?? []).some((p) => p.id !== s.incident.id && !p.ended_at);
  return <div className="patient-roster w-full border-t border-border-subtle pt-2">
    <PatientStrip patients={s.patients ?? []} activePatient={s.active_patient ?? s.incident.id} disabled={disabled || busy} onActivate={(id) => void perform(() => api.activatePatient(id))} />
    <details open={expanded || undefined}><summary className="min-h-12 cursor-pointer py-3 text-meta">Patients at this scene</summary>
      <p className="pb-2 text-body text-text-muted">Name and date of birth are optional. Use a temporary label; spoken identity can be reviewed when it becomes available. Capture follows the selected patient.</p>
      <form className="flex flex-wrap gap-3 pb-2" onSubmit={(e) => { e.preventDefault(); void perform(() => api.addPatient(label.trim() || `Patient ${(s.patients?.length ?? 0) + 1}`)); }}>
        <label className="text-meta">Label (optional)<input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={`Patient ${(s.patients?.length ?? 0) + 1}`} className="ml-2 min-h-12 rounded-lg border border-border-control bg-surface-2 px-3" /></label>
        <Button type="submit" disabled={disabled || busy}>Add patient at this scene</Button>
      </form>
      <p className="text-body text-text-muted">This keeps the other patients and their ED updates at this scene.</p>
    </details>
    {expanded && <section className="encounter-card"><h2>Next encounter</h2>
      <p>Finish this scene and begin a fresh record. Previous records and authorized delivery queues stay on this vehicle.</p>
      {anotherOpen && <p>Other patients at this scene are still open. Finish each encounter before starting a new scene.</p>}
      <button className="cabin-button" disabled={disabled || busy || anotherOpen} onClick={() => setUi({ confirmNewIncident: true })}>{s.incident.ended_at ? "Start next encounter…" : "Finish encounter and start next…"}</button>
    </section>}
  </div>;
}
