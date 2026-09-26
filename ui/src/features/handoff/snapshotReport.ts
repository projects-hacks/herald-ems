// A recorded replay has no Herald server, so no /api/handoff: this builds the same report shape from the recorded
// snapshot's confirmed facts, so the page shows one report either way. Unconfirmed values never appear in it. Each
// fact is its own line and carries its source (who, when), like the server's lines; times stay out of the text.
import { factValue, hhmm, patientLabel } from "@/lib/format";
import { allFacts, clinicianReceipt } from "@/lib/selectors";
import type { FactView, HandoffLine, HandoffReportData, HandoffSource, Snapshot } from "@/lib/types";

function confirmed(s: Snapshot, key: string) {
  const fact = s.facts[key];
  return fact?.status === "confirmed" ? fact : undefined;
}

function source(f: FactView): HandoffSource {
  return { fact_id: f.id, key: f.key, role: f.role, speaker: f.speaker, captured_by: f.captured_by, ts: f.ts,
    audio_id: f.provenance?.audio_id ?? null, photo_id: f.provenance?.photo_id ?? null };
}

function line(facts: FactView[], text: string): HandoffLine {
  return { kind: "fact", text, status: "confirmed", keys: facts.map((f) => f.key), fact_ids: facts.map((f) => f.id), sources: facts.map(source) };
}

/** One line per confirmed fact; systolic and diastolic blood pressure read as one ("Blood pressure: 182/104 mmHg"). */
function factLines(facts: (FactView | undefined)[]): HandoffLine[] {
  const present = facts.filter((f): f is FactView => !!f);
  const dbp = present.find((f) => f.key === "vitals.dbp");
  return present.flatMap((f) => {
    if (f.key === "vitals.dbp" && present.some((p) => p.key === "vitals.sbp")) return [];
    if (f.key === "vitals.sbp" && dbp) return [line([f, dbp], `Blood pressure: ${f.value}/${factValue(dbp)}`)];
    return [line([f], `${f.label}: ${factValue(f)}`)];
  });
}

export function snapshotReport(s: Snapshot): HandoffReportData {
  const vitals = ["vitals.sbp", "vitals.dbp", "vitals.hr", "vitals.rr", "vitals.spo2", "vitals.glucose", "vitals.temp", "vitals.consciousness"];
  const rows: [string, HandoffLine[], string][] = [
    ["Patient", factLines(["patient.name", "patient.identifier", "patient.age", "patient.sex"].map((k) => confirmed(s, k))),
      `${patientLabel(s)} · identity not confirmed · started ${hhmm(s.incident.started)}`],
    ["Problem", factLines(["complaint.chief", "symptom.onset", "stroke.lkw"].map((k) => confirmed(s, k))), "Chief complaint not captured"],
    ["Findings", factLines(["stroke.deficits", "scene.notes", "code_status"].map((k) => confirmed(s, k))), "No confirmed findings captured"],
    ["Latest vitals", factLines(vitals.map((k) => confirmed(s, k))), "No confirmed vitals captured"],
    ["History", factLines(["allergies", "meds.anticoagulant", "meds.list"].map((k) => confirmed(s, k))), "Allergies and medications not captured"],
    ["Transport", factLines(["transport.destination", "transport.eta_min"].map((k) => confirmed(s, k))), "Destination and ETA not captured"],
    ["Documented events", factLines(allFacts(s).filter((f) => ["meds.given", "procedures.done"].includes(f.key) && f.status === "confirmed")),
      "No confirmed medications or procedures captured"],
  ];
  const sections = rows.map(([label, lines, missing]) => ({
    id: label.toLowerCase().replace(/\s+/g, "-"), label,
    lines: lines.length ? lines : [{ text: missing, status: "missing" }],
  }));
  const times = allFacts(s).filter((f) => f.status === "confirmed").map((f) => f.ts).sort();
  // the open checklists' gaps, like the server's not_yet_known; an item heard but not yet confirmed waits in the
  // confirm list instead
  const checklist = new Set(s.readiness.flatMap((r) => r.items.map((i) => i.key)));
  const gaps = [...new Map([...s.needs_attention.missing.filter((g) => checklist.has(g.key)), ...s.needs_attention.unknown]
    .filter((g) => !g.pending_confirm)
    .map((g) => [g.key, { key: g.key, label: g.label }])).values()];
  const unconfirmed = allFacts(s).filter((f) => f.status === "unconfirmed").map((f) => ({ key: f.key, label: f.label }));
  const asOf = times.at(-1) ?? s.incident.started;
  const text = ["HERALD HANDOFF DRAFT: review before use", `Incident: ${s.incident.id}`,
    `Built from a recorded scenario's confirmed facts, as of ${hhmm(asOf)} (capture time, not necessarily measurement or administration time).`,
    ...sections.map((sec) => `${sec.label}: ${sec.lines.map((l) => l.text).join(" · ")}`),
    `Unverified fields (excluded): ${unconfirmed.map((f) => f.label).join(", ") || "None"}`,
    `Missing fields: ${gaps.map((g) => g.label).join(", ") || "None in active checklists"}`,
    `Clinician acknowledgment: ${clinicianReceipt(s)}.`].join("\n\n");
  return {
    incident: { id: s.incident.id }, as_of: asOf, text,
    format: { id: "summary", label: "Summary", title: "Handoff summary" }, formats: [],
    sections, not_yet_known: gaps, not_yet_confirmed: unconfirmed, not_obtained: [],
  };
}
