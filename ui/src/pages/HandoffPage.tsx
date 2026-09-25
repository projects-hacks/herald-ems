// Clinician-first handoff: the report and unresolved patient information lead; transport plumbing is secondary.
import { AlertCircle, CheckCircle2, ChevronDown, ClipboardList, Download, ListOrdered, Radio, Send, UserCheck } from "lucide-react";
import { factValue, patientLabel, hhmm } from "@/lib/format";
import { HandoffReport as StructuredHandoffReport } from "@/features/handoff/HandoffReport";
import { allFacts, reconciled } from "@/lib/selectors";
import { useHerald } from "@/lib/store";
import type { FactView, Snapshot } from "@/lib/types";
import { Badge, Button, Card, CardHeader, Count, EmptyState, PageHeader } from "@/components/kit";
import { AuthorizeForm, LinkDownNote, PacketLog, SyncTable, useHandoff } from "@/features/handoff/handoff";

function confirmed(s: Snapshot, key: string) {
  const fact = s.facts[key];
  return fact?.status === "confirmed" ? fact : undefined;
}

function joinFacts(facts: (FactView | undefined)[]) {
  return facts.filter(Boolean).map((fact) => `${fact!.label}: ${factValue(fact!)} (${hhmm(fact!.ts)})`).join(" · ");
}

function HandoffReport({ s }: { s: Snapshot }) {
  const patient = joinFacts([confirmed(s, "patient.name"), confirmed(s, "patient.identifier"), confirmed(s, "patient.age"), confirmed(s, "patient.sex")]);
  const problem = joinFacts([confirmed(s, "complaint.chief"), confirmed(s, "symptom.onset"), confirmed(s, "stroke.lkw")]);
  const findings = joinFacts([confirmed(s, "stroke.deficits"), confirmed(s, "scene.notes"), confirmed(s, "code_status")]);
  const vitals = joinFacts(["vitals.sbp", "vitals.dbp", "vitals.hr", "vitals.rr", "vitals.spo2", "vitals.glucose", "vitals.temp", "vitals.consciousness"].map((key) => confirmed(s, key)));
  const history = joinFacts([confirmed(s, "allergies"), confirmed(s, "meds.anticoagulant"), confirmed(s, "meds.list")]);
  const transport = joinFacts([confirmed(s, "transport.destination"), confirmed(s, "transport.eta_min")]);
  const treatments = joinFacts(allFacts(s).filter((f) => ["meds.given", "procedures.done"].includes(f.key) && f.status === "confirmed"));
  const rows = [
    ["Patient", patient || `${patientLabel(s)} · identity not confirmed · started ${hhmm(s.incident.started)}`],
    ["Problem", problem || "Chief complaint not captured"],
    ["Findings", findings || "No confirmed findings captured"],
    ["Latest vitals", vitals || "No confirmed vitals captured"],
    ["History", history || "Allergies and medications not captured"],
    ["Transport", transport || "Destination and ETA not captured"],
    ["Documented events", treatments || "No confirmed medications or procedures captured"],
  ];
  const missing = s.needs_attention.missing.length + s.needs_attention.unknown.length;
  const unresolved = allFacts(s).filter((fact) => fact.status === "unconfirmed");
  const gaps = [...s.needs_attention.missing, ...s.needs_attention.unknown];
  const download = () => {
    const report = ["HERALD HANDOFF DRAFT — review before use", `Incident: ${s.incident.id}`,
      `Prepared: ${new Date().toISOString()}`, "Times are capture times, not necessarily measurement or administration times. This is a snapshot summary, not the full MIST/SBAR report.",
      ...rows.map(([label, value]) => `${label}: ${value}`),
      `Unverified fields (excluded): ${unresolved.map((fact) => fact.label).join(", ") || "None"}`,
      `Missing fields: ${gaps.map((item) => item.label).join(", ") || "None in active checklists"}`,
      "Clinician acknowledgment: not recorded. This draft is not a complete incident archive."].join("\n\n");
    const url = URL.createObjectURL(new Blob([report], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `herald-${s.incident.id}-draft.txt`;
    link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Card aria-labelledby="report-h">
    <CardHeader icon={ClipboardList} cat="ed" title="Read-aloud handoff" id="report-h"
      subtitle="Snapshot summary · confirmed facts and events · times show capture, not measurement or administration"
      actions={missing ? <Badge tone="medium" icon={AlertCircle}>{missing} gaps</Badge> : <Badge icon={CheckCircle2}>Review draft</Badge>} />
    <dl className="px-5 pb-5">
      {rows.map(([label, value]) => <div key={label} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 border-t border-border-subtle py-3 first:border-t-0">
        <dt className="text-meta font-semibold text-text-muted">{label}</dt>
        <dd className="text-body font-medium text-text-primary">{value}</dd>
      </div>)}
    </dl>
    <div className="flex flex-col gap-3 border-t border-border-subtle px-5 py-4">
      {unresolved.length > 0 && <p className="text-body text-medium-fg">Needs verification: {unresolved.map((fact) => fact.label).join(" · ")}. These values are excluded from the draft.</p>}
      {gaps.length > 0 && <p className="text-body text-text-muted">Still missing: {gaps.map((item) => item.label).join(" · ")}</p>}
      <div><Button onClick={download}><Download size={17} />Download handoff draft</Button></div>
    </div>
  </Card>;
}

function ReceiptStatus({ s }: { s: Snapshot }) {
  const r = s.relay;
  const clinician = r.clinician_acknowledgements?.[s.incident.id]?.at(-1);
  const held = allFacts(s).filter((fact) => fact.status === "unconfirmed").length;
  const technical = reconciled(s);
  return <Card className="p-5" aria-label="Handoff receipt">
    <div className="flex items-start gap-3">
      <UserCheck size={22} className="mt-0.5 shrink-0 text-cat-ed-fg" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2"><h2 className="text-title font-semibold">Receipt</h2>
          <Badge tone={technical && !held ? "ok" : r.link === "down" ? "low" : "medium"}>{technical ? held ? `${held} facts still need verification` : "Confirmed updates delivered" : r.link === "down" ? "Waiting for link" : "Sending updates"}</Badge>
        </div>
        <p className="mt-1 text-body text-text-muted">{clinician
          ? `Receiving team: ${clinician.status === "cath_lab_activated" ? "Cath lab activated" : "Received"}${clinician.note ? ` · ${clinician.note}` : ""}`
          : "Human acknowledgment is not recorded. Technical delivery does not mean a clinician has viewed the handoff."}</p>
      </div>
    </div>
  </Card>;
}

export function HandoffPage() {
  const s = useHerald((st) => st.snapshot);
  const isReplay = useHerald((st) => st.source === "fixture");
  const h = useHandoff(s);
  if (!s) return null;
  const r = s.relay;
  const header = <PageHeader title="Handoff" description={r.authorized ? `Preparing handoff to ${r.authorized.destination}` : "Review the patient story, resolve missing information, then authorize the pre-alert."} />;
  const wrap = (body: React.ReactNode) => <div className="flex flex-col gap-5 px-6 pt-5 pb-6">{header}{body}</div>;
  // A replay has no /api/handoff to fetch: lead with the snapshot summary, expanded, instead of the empty fetched card.
  const report = isReplay ? <HandoffReport s={s} />
    : <><StructuredHandoffReport /><details><summary className="min-h-12 p-3">Snapshot summary and text export</summary><HandoffReport s={s} /></details></>;
  if (!r.configured) return wrap(<>{report}<Card><EmptyState icon={Send} cat="ed" title="The receiving link is not set up">The read-aloud report remains available. Ask your system administrator to connect the receiving department.</EmptyState></Card></>);
  if (!r.authorized) return wrap(<>{report}<Card className="max-w-lg p-5"><AuthorizeForm s={s} /></Card></>);
  return wrap(<>
    {report}
    {r.link === "down" && <LinkDownNote />}
    <ReceiptStatus s={s} />
    <Card aria-labelledby="fields-h">
      <CardHeader icon={ListOrdered} cat="ed" title="Delivery status" id="fields-h" subtitle="Sent to the receiving system, queued, or held for verification" actions={<Count n={h.rows.length} />} />
      <SyncTable s={s} rows={h.rows} />
    </Card>
    <details className="card group">
      <summary className="flex min-h-14 cursor-pointer list-none items-center gap-2 px-5 text-title font-semibold text-text-secondary">
        <Radio size={17} className="text-text-muted" />Technical diagnostics
        <span className="ml-auto text-meta font-normal text-text-muted">{r.packets_acked} packets · {r.retries} retries</span>
        <ChevronDown size={17} className="transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-border-subtle"><PacketLog s={s} /></div>
    </details>
  </>);
}
