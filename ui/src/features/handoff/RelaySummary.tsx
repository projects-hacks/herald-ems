import { activeSync, allFacts, clinicianReceipt } from "@/lib/selectors";
import { useHerald } from "@/lib/store";

/** Counts belong to the active patient; a system acknowledgment is not a clinician receipt. */
export function RelaySummary() {
  const s = useHerald((state) => state.snapshot);
  const sync = s ? Object.values(activeSync(s)) : [];
  const counts = [
    { label: "Delivered fields", value: sync.filter((status) => status === "sent").length, tone: "sent" },
    { label: "Queued fields", value: sync.filter((status) => status === "queued").length, tone: "queued" },
    { label: "Held for review", value: s ? allFacts(s).filter((fact) => fact.status === "unconfirmed").length : 0, tone: "held" },
  ];
  return <div className="handoff-summary">
    <p>{!s ? "Waiting for relay status" : s.relay.authorized ? "Sharing authorized" : "Sharing not authorized · confirmed facts stay on this vehicle"}</p>
    <dl className="relay-summary" aria-label="Active patient sharing status">
      {counts.map(({ label, value, tone }) => <div key={tone} data-state={tone}><dt>{label}</dt><dd>{s ? value : "—"}</dd></div>)}
    </dl>
    <p className="workspace-caption">Raw audio, photos and unverified facts stay on this vehicle. Delivery confirms system receipt; {s ? clinicianReceipt(s) : "clinician receipt unknown"}.</p>
  </div>;
}
