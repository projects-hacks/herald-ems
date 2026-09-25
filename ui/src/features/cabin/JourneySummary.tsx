import { Activity, Clock3, Pill } from "lucide-react";
import { allFacts } from "@/lib/selectors";
import { factValue, hhmm, sourceName } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { useContract } from "@/lib/contract";

/** The journey is a history of observations, never an inferred cause or treatment recommendation. */
export function JourneySummary({ onReview, onTrends }: { onReview: () => void; onTrends: () => void }) {
  const s = useHerald((state) => state.snapshot);
  const contract = useContract();
  const changes = s?.changed.filter((change) => change.significant) ?? [];
  const events = s ? allFacts(s).filter((fact) => ["meds.given", "procedures.done"].includes(fact.key) && fact.status !== "rejected")
    .sort((a, b) => b.ts.localeCompare(a.ts)) : [];
  return <section className="journey-summary" aria-label="Patient journey">
    <div className="journey-changes">
      <h2><Activity size={20} />Changes during the journey</h2>
      {!s ? <p>Waiting for patient observations.</p> : changes.length ? <ul>{changes.map((change) => <li key={change.key}>
        <strong>{change.label}: {change.series.join(" → ")} {contract?.keys[change.key]?.unit}</strong>
        <span>{hhmm(change.times[0])}–{hhmm(change.times.at(-1))} · confirmed readings</span>
        <p>{contract?.changeRules[change.key]}</p>
      </li>)}</ul> : <p>No significant changes established from confirmed readings. Missing or unverified observations cannot establish stability.</p>}
      <button className="cabin-button" onClick={onTrends}>View journey trends</button>
    </div>
    <div className="journey-events">
      <h2><Pill size={20} />Care recorded along the way</h2>
      {events.length ? <ol>{events.slice(0, 4).map((fact) => <li key={fact.id} data-state={fact.status}>
        <strong>{factValue(fact)}</strong>
        <span><Clock3 size={14} />Recorded {hhmm(fact.ts)} · {sourceName(fact)}</span>
        <span>{fact.status === "confirmed" ? "Confirmed · included in handoff" : "Needs verification · kept on vehicle"}</span>
      </li>)}</ol> : <p>No medication administration or procedure recorded yet. A visible label alone does not establish that a medicine was given.</p>}
      {events.some((fact) => fact.status === "unconfirmed") && <button className="cabin-button" onClick={onReview}>Review recorded care</button>}
    </div>
  </section>;
}
