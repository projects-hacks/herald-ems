// Who told us what: the report's `informants` (herald/reporting/informants.py). A recording or a server from before
// 2026-09-26 does not send them, so the same grouping is derived here from the confirmed lines' sources: the people
// other than the crew first, then the patient monitor, then the crew, and what could not be attributed last.
import type { HandoffInformant, HandoffReportData, HandoffSection } from "@/lib/types";

// How a source is named when no speaker word is used: the server's config/handoff.yaml `informants.labels`
const WHO: Record<string, string> = {
  medic: "medic", patient: "patient", device: "patient monitor", photo: "photo", family: "family",
  bystander: "bystander", unknown: "speaker not identified",
};
// the reading order (herald/reporting/informants.py _ORDER)
const ORDER: Record<string, number> = { family: 0, bystander: 0, patient: 1, device: 2, photo: 3, medic: 4, unknown: 5 };

/** [{who, role, keys, items}] from the confirmed lines' sources; `label` names a key ("Medications"). */
export function deriveInformants(sections: HandoffSection[], label: (key: string) => string): HandoffInformant[] {
  const groups = new Map<string, HandoffInformant>();
  for (const line of sections.flatMap((section) => section.lines)) {
    if (line.status !== "confirmed") continue;
    for (const src of line.sources ?? []) {
      const role = src.role || "unknown";
      const named = (role === "family" || role === "bystander") && !!src.speaker;
      const id = named ? `${role}:${src.speaker}` : role;
      const group = groups.get(id) ?? { who: named ? String(src.speaker) : WHO[role] ?? role, role, keys: [], items: [] };
      groups.set(id, group);
      if (!group.keys.includes(src.key)) group.keys.push(src.key);
    }
  }
  const rows = [...groups.values()].sort((a, b) => (ORDER[a.role] ?? 0) - (ORDER[b.role] ?? 0));
  for (const row of rows) row.items = [...new Set(row.keys.map(label))];
  return rows;
}

/** The server's list when it sent one; otherwise the same list derived from the report's lines. */
export function reportInformants(r: HandoffReportData, label: (key: string) => string): HandoffInformant[] {
  return r.informants ?? deriveInformants(r.sections, label);
}
