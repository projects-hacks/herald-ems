import { ChevronRight, CircleCheck, CircleDashed, CircleHelp, ClipboardList, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useHerald } from "@/lib/store";
import { factValue } from "@/lib/format";
import type { ReadinessItem } from "@/lib/types";

const STATE = { done: { icon: CircleCheck, text: "Captured" }, pending: { icon: CircleHelp, text: "Verify" }, missing: { icon: CircleDashed, text: "Missing" } };

export function PatientSafetySummary({ onReview }: { onReview: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const facts = [s?.facts["allergies"], s?.facts["meds.anticoagulant"], s?.facts["code_status"]].filter((f) => f !== undefined);
  if (!facts.length) return null;
  return <div className="patient-safety-summary" aria-label="Key patient information">{facts.map((fact) => <button key={fact.id} onClick={onReview}>
    <ShieldAlert size={16} /><span>{fact.label}: <strong>{fact.status === "confirmed" ? factValue(fact) : "Needs verification"}</strong></span><ChevronRight size={14} />
  </button>)}</div>;
}

export function CareSummary({ onReview }: { onReview: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const [selected, setSelected] = useState("");
  const readiness = s?.readiness.find((r) => r.id === selected) ?? s?.readiness[0];
  return <section className="care-readiness" aria-label="Pre-alert readiness">
    <div className="workspace-card-heading"><span className="workspace-icon"><ClipboardList size={21} /></span><div><h3>Pre-alert readiness</h3><p>Every detail counts for the receiving team</p></div>
      {readiness && <span className={`readiness-badge ${readiness.ready ? "complete" : ""}`}>{readiness.ready ? "Captured" : `${readiness.total - readiness.done} to capture`}</span>}
    </div>
    {readiness ? <>
      <div className="readiness-title">{s!.readiness.length > 1 ? <select aria-label="Pre-alert checklist" value={readiness.id} onChange={(event) => setSelected(event.target.value)}>{s!.readiness.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select> : <strong>{readiness.label}</strong>}
        <span><b>{readiness.done}</b> / {readiness.total} captured</span></div>
      <div className="readiness-progress" aria-hidden>{readiness.items.map((item) => <span key={item.key} data-state={item.state} />)}</div>
      <ul className="readiness-list">{readiness.items.map((item: ReadinessItem) => { const state = STATE[item.state]; return <li key={item.key} data-state={item.state}>
        <state.icon size={17} /><span>{item.label}</span><small>{state.text}</small>
      </li>; })}</ul>
      <button className="readiness-action" onClick={onReview}>Review gaps & evidence<ChevronRight size={17} /></button>
    </> : <div className="readiness-empty"><ClipboardList size={30} /><strong>Ready when you are</strong><p>Record the dispatch to surface the relevant pre-alert checklist.</p></div>}
  </section>;
}
