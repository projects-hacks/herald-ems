import { useState } from "react";
import { useHerald } from "@/lib/store";
import { api } from "@/lib/api";
import { PatientStrip } from "./PatientStrip";
import { Button } from "./kit";

export function PatientRoster() {
  const s = useHerald((state) => state.snapshot);
  const disabled = useHerald((state) => state.source === "fixture" || state.stale || state.conn !== "open");
  const [busy, setBusy] = useState(false), [label, setLabel] = useState("");
  async function perform(action: () => Promise<boolean>) {
    if (busy || disabled) return;
    setBusy(true);
    try { if (!await action()) useHerald.getState().showToast("Patient action failed. Check the active patient before continuing."); else setLabel(""); }
    finally { setBusy(false); }
  }
  if (!s) return null;
  return <div className="w-full border-t border-border-subtle pt-2">
    <PatientStrip patients={s.patients ?? []} activePatient={s.active_patient ?? s.incident.id} disabled={disabled || busy} onActivate={(id) => void perform(() => api.activatePatient(id))} />
    <details><summary className="min-h-12 cursor-pointer py-3 text-meta">Mass-casualty · add patient</summary>
      <form className="flex flex-wrap gap-3 pb-2" onSubmit={(e) => { e.preventDefault(); void perform(() => api.addPatient(label.trim())); }}>
        <label className="text-meta">Patient label<input required value={label} onChange={(e) => setLabel(e.target.value)} className="ml-2 min-h-12 rounded-lg border border-border-control bg-surface-2 px-3" /></label>
        <Button type="submit" disabled={disabled || busy || !label.trim()}>Add patient</Button>
      </form>
    </details>
  </div>;
}
