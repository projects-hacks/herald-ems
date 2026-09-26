// The handoff, built around one moment: handing the patient over. Top to bottom: a header card (who, why, where, and
// what the ED has); what is left to decide, as one line that opens (never blocking); the report as the receiving team
// hears it, with the latest vitals and who told us what beside it; and the hand over action, always in reach. After the hand over, the page says so and offers the next patient.
// Delivery plumbing (per-field status, packets) is only in the detailed application view.
import { useState } from "react";
import { ChevronDown, ListOrdered, Radio } from "lucide-react";
import { Badge, Card, CardHeader, Count } from "@/components/kit";
import { reconciled, reconciledDuplicates } from "@/lib/selectors";
import { BeforeHandover } from "@/features/handoff/BeforeHandover";
import { HandedOver } from "@/features/handoff/HandedOver";
import { HandoffReportView, useHandoffReport } from "@/features/handoff/HandoffReport";
import { HandoverBar } from "@/features/handoff/HandoverBar";
import { PacketLog, SyncTable, useHandoff } from "@/features/handoff/handoff";
import { useNow } from "@/hooks/useNow";
import { factValue, hhmm } from "@/lib/format";
import { etaSeconds, handoverDestination, patientIdentity, preAlertStatus } from "@/lib/handover";
import { useHerald } from "@/lib/store";
import { destinationHow } from "@/features/transport/DestinationStatus";
import type { Snapshot } from "@/lib/types";
import "@/features/handoff/handoff.css";

/** The header card: who (confirmed identity, age and sex), why (the confirmed chief complaint), where and when (the
 *  destination and ETA), and what the ED has (the pre-alert status). Confirmed facts only; a gap says so. */
function Headline({ s }: { s: Snapshot }) {
  const at = useHerald((st) => st.lastStateAt);
  const now = useNow();
  const dest = handoverDestination(s);
  const handed = !!s.incident.handed_over_at;
  const eta = handed || s.incident.arrived_at ? null : etaSeconds(s, at, now);
  const status = preAlertStatus(s);
  const source = s.clocks.find((clock) => clock.id === "eta")?.source;
  const how = !handed && s.transport?.destination ? destinationHow(s.transport.destination) : null;
  const complaint = s.facts["complaint.chief"]?.status === "confirmed" ? factValue(s.facts["complaint.chief"]) : null;
  return <header className="handoff-headline">
    <div className="handoff-who">
      <p className="label-caps text-text-muted">Handoff</p>
      <h1>{patientIdentity(s)}</h1>
      {!handed && <p className="handoff-chip" data-tone={status.tone} role="status">{status.text}</p>}
    </div>
    <dl className="handoff-facts">
      <div><dt>Chief complaint</dt><dd data-missing={!complaint || undefined}>{complaint ?? "Not yet known"}</dd></div>
      <div><dt>Destination</dt><dd data-missing={!dest || undefined}>{dest ? `${dest}${how ? ` (${how})` : ""}` : "Not set: say the hospital"}</dd></div>
      {s.incident.arrived_at && !handed ? <div><dt>Arrived</dt><dd className="num">{hhmm(s.incident.arrived_at)}</dd></div>
        : eta !== null && <div><dt>ETA</dt><dd><span className="num">{eta > 0 ? `${Math.max(1, Math.round(eta / 60))} min` : "now"}</span>
          {source === "route" ? <small> by road route</small> : source === "crew" ? <small> crew estimate</small> : null}</dd></div>}
    </dl>
  </header>;
}

/** Per-field delivery and the packet log: the detailed application view only, never on the medic's screen. */
function DeliveryDetails({ s }: { s: Snapshot }) {
  const h = useHandoff(s);
  if (!s.relay.authorized) return null;
  const dupes = reconciledDuplicates(s);
  return <>
    <Card aria-labelledby="fields-h">
      <CardHeader icon={ListOrdered} cat="ed" title="Delivery status" id="fields-h" subtitle="Sent to the receiving system, queued, or held for verification"
        actions={<>{reconciled(s) && dupes !== null && <Badge tone="neutral">reconciled · {dupes} duplicate{dupes === 1 ? "" : "s"}</Badge>}<Count n={h.rows.length} /></>} />
      <SyncTable s={s} rows={h.rows} />
    </Card>
    <details className="card group">
      <summary className="flex min-h-14 cursor-pointer list-none items-center gap-2 px-5 text-title font-semibold text-text-secondary">
        <Radio size={17} className="text-text-muted" />Technical diagnostics
        <span className="ml-auto text-meta font-normal text-text-muted">{s.relay.packets_acked} packets · {s.relay.retries} retries</span>
        <ChevronDown size={17} className="transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-border-subtle"><PacketLog s={s} /></div>
    </details>
  </>;
}

/** `onNotes` opens typing (the Now screen passes its notes panel); `reportOpen` shows the handed-over report at once. */
export function HandoffPage({ onNotes, reportOpen = false }: { onNotes?: () => void; reportOpen?: boolean } = {}) {
  const s = useHerald((st) => st.snapshot);
  const explain = useHerald((st) => st.ui.mode === "explain");
  const setUi = useHerald((st) => st.setUi);
  const h = useHandoffReport();
  const [showReport, setShowReport] = useState(reportOpen);
  if (!s) return null;
  const handed = !!s.incident.handed_over_at;
  const obtained = new Set(s.incident.not_obtained ?? []);
  const missing = (h.report?.not_yet_known ?? []).filter((m) => !obtained.has(m.key)).length;
  return <div className="handoff-page" data-handed-over={handed || undefined}>
    <Headline s={s} />
    {handed ? <>
      <HandedOver s={s} reportOpen={showReport} onViewReport={() => setShowReport(!showReport)} />
      {showReport && <HandoffReportView h={h} />}
    </> : <>
      <BeforeHandover s={s} report={h.report} onReport={h.accept} onNotes={onNotes ?? (() => setUi({ page: "transcript" }))} />
      <HandoffReportView h={h} />
    </>}
    {explain && <DeliveryDetails s={s} />}
    {!handed && <HandoverBar s={s} report={h.report} missing={missing} />}
  </div>;
}
