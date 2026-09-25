import { useState } from "react";
import { Activity, CircleCheck, CircleDashed, CircleHelp, Droplets, Gauge, HeartPulse, Maximize2, Minimize2, Wind } from "lucide-react";
import { Sparkline } from "@/components/Sparkline";
import { catOf } from "@/lib/categories";
import { useContract } from "@/lib/contract";
import { factValue, hhmm, sourceName } from "@/lib/format";
import { useHerald } from "@/lib/store";

const VITALS = [{ key: "vitals.hr", icon: HeartPulse }, { key: "vitals.sbp", icon: Gauge }, { key: "vitals.spo2", icon: Droplets }, { key: "vitals.rr", icon: Wind }];
export function VitalReadings({ onReview, onTrends }: { onReview: () => void; onTrends: () => void }) {
  const s = useHerald((state) => state.snapshot);
  const stale = useHerald((state) => state.source !== "fixture" && (state.stale || state.conn !== "open"));
  const contract = useContract();
  const [expanded, setExpanded] = useState<string | null>(null);
  return <section className="readings-group" aria-label="Latest documented readings">
    <div className="cabin-section-label"><div><h2><Activity size={18} />Documented readings</h2><p>Recorded values, not a live monitor</p></div>
      <button className="cabin-button" onClick={onTrends}>Trends & scores</button></div>
    <div className="cabin-vitals">
      {VITALS.map(({ key, icon: Icon }) => {
        const fact = s?.facts[key];
        const confirmed = fact?.status === "confirmed" && fact.value !== null;
        const label = contract?.keys[key]?.label ?? fact?.label ?? key.split(".").at(-1)?.toUpperCase();
        const large = expanded === key;
        const Status = confirmed ? CircleCheck : fact ? CircleHelp : CircleDashed;
        const history = [...(s?.timeline ?? [])].filter((item) => item.key === key && item.status === "confirmed").reverse();
        return <article key={key} className={`cabin-vital ${!confirmed ? "unknown" : ""} ${large ? "is-expanded" : ""}`}>
          <div className="cabin-vital-label"><span className="vital-label-group"><span className="vital-category-icon" data-cat={catOf(key)}><Icon size={16} /></span>{label}</span><button className="component-expand" aria-label={`${large ? "Collapse" : "Expand"} ${label}`} aria-expanded={large} onClick={() => setExpanded(large ? null : key)}>{large ? <Minimize2 size={18} /> : <Maximize2 size={18} />}</button></div>
          <div className="vital-number-row"><div className="cabin-vital-value">{confirmed ? String(fact.value) : "—"}<small>{fact?.unit ?? contract?.keys[key]?.unit}</small></div>{confirmed && history.length > 1 && <Sparkline values={history.slice(0, 8).reverse().map((item) => item.value).filter((value): value is number => typeof value === "number")} width={66} height={26} label={`${label}: recent confirmed readings`} />}</div>
          <p className="cabin-vital-meta"><Status size={12} aria-hidden />{fact ? `${confirmed ? "Confirmed" : "Needs verification"} · recorded ${hhmm(fact.ts)}` : "Not captured"}{stale ? " · disconnected" : ""}</p>
          {large && <div className="vital-history"><h3>Recent confirmed readings</h3>
            {history.length ? <ol>{history.slice(0, 5).map((item) => <li key={item.id}><time>{hhmm(item.ts)}</time><strong>{factValue(item)}</strong><span>{sourceName(item)}</span></li>)}</ol> : <p>No confirmed history available.</p>}
            {!confirmed && <button className="cabin-button" onClick={onReview}>Review missing or unverified information</button>}
            <button className="cabin-button" onClick={onTrends}>Open trends & evidence</button>
          </div>}
        </article>;
      })}
    </div>
  </section>;
}
