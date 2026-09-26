// A recorded replay has no Herald server, so no /api/handoff: this builds the same report shape from the recorded
// snapshot's confirmed facts, so the page shows one report either way. Unconfirmed values never appear in it.
import { factValue, hhmm, patientLabel } from "@/lib/format";
import { allFacts, clinicianReceipt } from "@/lib/selectors";
import type { FactView, HandoffReportData, Snapshot } from "@/lib/types";

function confirmed(s: Snapshot, key: string) {
  const fact = s.facts[key];
  return fact?.status === "confirmed" ? fact : undefined;
}

function joinFacts(facts: (FactView | undefined)[]) {
  return facts.filter(Boolean).map((fact) => `${fact!.label}: ${factValue(fact!)} (${hhmm(fact!.ts)})`).join(" · ");
}

export function snapshotReport(s: Snapshot): HandoffReportData {
  const vitals = ["vitals.sbp", "vitals.dbp", "vitals.hr", "vitals.rr", "vitals.spo2", "vitals.glucose", "vitals.temp", "vitals.consciousness"];
  const rows: [string, string, string][] = [
    ["Patient", joinFacts(["patient.name", "patient.identifier", "patient.age", "patient.sex"].map((k) => confirmed(s, k))),
      `${patientLabel(s)} · identity not confirmed · started ${hhmm(s.incident.started)}`],
    ["Problem", joinFacts(["complaint.chief", "symptom.onset", "stroke.lkw"].map((k) => confirmed(s, k))), "Chief complaint not captured"],
    ["Findings", joinFacts(["stroke.deficits", "scene.notes", "code_status"].map((k) => confirmed(s, k))), "No confirmed findings captured"],
    ["Latest vitals", joinFacts(vitals.map((k) => confirmed(s, k))), "No confirmed vitals captured"],
    ["History", joinFacts(["allergies", "meds.anticoagulant", "meds.list"].map((k) => confirmed(s, k))), "Allergies and medications not captured"],
    ["Transport", joinFacts(["transport.destination", "transport.eta_min"].map((k) => confirmed(s, k))), "Destination and ETA not captured"],
    ["Documented events", joinFacts(allFacts(s).filter((f) => ["meds.given", "procedures.done"].includes(f.key) && f.status === "confirmed")),
      "No confirmed medications or procedures captured"],
  ];
  const sections = rows.map(([label, value, missing]) => ({
    id: label.toLowerCase().replace(/\s+/g, "-"), label,
    lines: [{ text: value || missing, status: value ? "confirmed" : "missing" }],
  }));
  // the open checklists' gaps, like the server's not_yet_known; an item heard but not yet confirmed waits in the
  // confirm list instead
  const checklist = new Set(s.readiness.flatMap((r) => r.items.map((i) => i.key)));
  const gaps = [...new Map([...s.needs_attention.missing.filter((g) => checklist.has(g.key)), ...s.needs_attention.unknown]
    .filter((g) => !g.pending_confirm)
    .map((g) => [g.key, { key: g.key, label: g.label }])).values()];
  const unconfirmed = allFacts(s).filter((f) => f.status === "unconfirmed").map((f) => ({ key: f.key, label: f.label }));
  const text = ["HERALD HANDOFF DRAFT — review before use", `Incident: ${s.incident.id}`,
    "Built from a recorded scenario's confirmed facts. Times are capture times, not necessarily measurement or administration times.",
    ...sections.map((sec) => `${sec.label}: ${sec.lines[0].text}`),
    `Unverified fields (excluded): ${unconfirmed.map((f) => f.label).join(", ") || "None"}`,
    `Missing fields: ${gaps.map((g) => g.label).join(", ") || "None in active checklists"}`,
    `Clinician acknowledgment: ${clinicianReceipt(s)}.`].join("\n\n");
  return {
    incident: { id: s.incident.id }, as_of: s.incident.started, text,
    format: { id: "summary", label: "Summary", title: "Handoff summary" }, formats: [],
    sections, not_yet_known: gaps, not_yet_confirmed: unconfirmed, not_obtained: [],
  };
}
