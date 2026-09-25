// Pure functions from the snapshot to what the screen shows. Tested in src/test/selectors.test.ts.
import type { Contract } from "./contract";
import type { Alert, FactView, Snapshot, StrokeScale, StrokeScaleId } from "./types";

// ---------- alert priority (UX_PLAN §2.3: IEC 60601-1-8 semantics, no sounds) ----------
export type Priority = "high" | "medium" | "low";
const RANK: Record<Priority, number> = { high: 0, medium: 1, low: 2 };

export function alertPriority(a: Alert): Priority {
  if (a.type === "news2_rise") return a.band === "high" ? "high" : a.band === "medium" || a.band === "low-medium" ? "medium" : "low";
  return "medium";   // contradiction, confirm_required, race_positive, gfast_positive, significant_change
}
/** Stable identity for "Seen": type + key + value (§2.3). */
export function alertKey(a: Alert): string {
  switch (a.type) {
    case "contradiction": case "confirm_required": return `${a.type}:${a.key}:${a.confirm_fact_id}`;
    case "significant_change": return `${a.type}:${a.key}:${a.series.join(",")}`;
    case "news2_rise": return `${a.type}:${a.from}->${a.to}`;
    case "race_positive": case "gfast_positive": return `${a.type}:${a.score}`;
  }
}
/** Contradictions and code-status confirmations can't be marked seen; they leave only when resolved. */
export function dismissable(a: Alert): boolean {
  return a.type !== "contradiction" && a.type !== "confirm_required";
}
/** Alert order (UX_PLAN §2.3): HIGH before MEDIUM before LOW, then the newest first by arrival on this screen (the
 *  server lists alerts by type, not time; without arrival data the later list position counts as newer). */
export function rankAlerts(alerts: Alert[], arrival: Record<string, number> = {}): Alert[] {
  return alerts.map((a, i) => ({ a, t: arrival[alertKey(a)] ?? i }))
    .sort((x, y) => RANK[alertPriority(x.a)] - RANK[alertPriority(y.a)] || y.t - x.t)
    .map((x) => x.a);
}

// ---------- needs attention (§3.1.6 and the alert slot §3.1.8, as one queue) ----------
/** Unconfirmed facts, minus those already shown in a contradiction or code-status alert; oldest first, the order
 *  they were heard. */
export function needsTap(s: Snapshot): FactView[] {
  const inAlert = new Set(s.alerts.flatMap((a) => ("facts" in a ? a.facts.map((f) => f.id) : [])));
  const all = new Map([...Object.values(s.facts), ...Object.values(s.events ?? {}).flat()].map((f) => [f.id, f]));
  return [...all.values()].filter((f) => f.status === "unconfirmed" && (!inAlert.has(f.id) || (f.verify?.status === "mismatch" && !f.verify.resolution)))
    .sort((a, b) => a.ts.localeCompare(b.ts));
}

/** Everything that waits on the medic, in the order they should handle it:
 *  urgent (HIGH, until seen) · choose (sources disagree: data held on the vehicle, P10) · confirm (code status, then
 *  facts that need a tap) · review (informational findings, until seen). Seen alerts move to "acknowledged". */
export interface Attention {
  urgent: Alert[]; choose: Alert[]; confirmAlerts: Alert[]; confirmFacts: FactView[]; review: Alert[]; acknowledged: Alert[];
  count: number;
}
export function attention(s: Snapshot, seen: Record<string, true>, arrival: Record<string, number> = {}, holdMark: number | null = null): Attention {
  // while push-to-talk is held, alerts that arrived after it was pressed wait (§3.1.8, P4)
  const shown = holdMark === null ? s.alerts : s.alerts.filter((a) => (arrival[alertKey(a)] ?? 0) <= holdMark);
  const ranked = rankAlerts(shown, arrival);
  const isSeen = (a: Alert) => dismissable(a) && !!seen[alertKey(a)];
  const open = ranked.filter((a) => !isSeen(a));
  const out = {
    urgent: open.filter((a) => dismissable(a) && alertPriority(a) === "high"),
    choose: open.filter((a) => a.type === "contradiction"),
    confirmAlerts: open.filter((a) => a.type === "confirm_required"),
    confirmFacts: needsTap(s),
    review: open.filter((a) => dismissable(a) && alertPriority(a) !== "high"),
    acknowledged: ranked.filter(isSeen),
  };
  return { ...out, count: out.urgent.length + out.choose.length + out.confirmAlerts.length + out.confirmFacts.length + out.review.length };
}
/** The tone of the attention count: HIGH if anything urgent, CHECK if anything else, calm when empty. */
export function attentionTone(a: Attention): Priority | null {
  return a.urgent.length ? "high" : a.count ? "medium" : null;
}

// ---------- scores ----------
export function strokeScales(s: Snapshot): { id: StrokeScaleId; scale: StrokeScale }[] {
  const ids = s.scores.stroke_scales?.length ? s.scores.stroke_scales : (["RACE"] as StrokeScaleId[]);
  return ids.map((id) => ({ id, scale: id === "GFAST" ? s.scores.gfast : s.scores.race }));
}
/** The field-triage card shows only for trauma or fall dispatches (TASKS P4.3). */
export function showFieldTriage(s: Snapshot): boolean {
  const text = `${s.incident.dispatch ?? ""} ${String(s.facts["complaint.chief"]?.value ?? "")}`.toLowerCase();
  return /\b(trauma|fall|fell|mvc|collision|crash|assault|injur)/.test(text);
}

// ---------- ER status (§3.1.9) ----------
export type ErRowState = "sent" | "queued" | "held";
export interface ErRow { key: string; state: ErRowState; seq: number | null; why: string; held: "tap" | "disagree" | null }

/** ED-set keys in relay-tier order, each sent / queued / held. Keys with nothing to send are omitted. */
export function erRows(s: Snapshot, c: Contract | null): ErRow[] {
  const tiers = c?.relayTiers ?? {};
  const keys = Object.keys(tiers).sort((a, b) => tiers[a].tier - tiers[b].tier);
  const disputed = new Set(s.alerts.filter((a) => a.type === "contradiction").map((a) => (a as { key: string }).key));
  const rows: ErRow[] = [];
  for (const key of keys) {
    const sync = s.relay.sync[key];
    const fact = s.facts[key];
    // Held wins: an unconfirmed newest value never counts as sent, even if an older confirmed value was
    // (e.g. the husband's "no allergies" went out; the daughter's "aspirin" is disputed and stays on the vehicle).
    if (fact && fact.status === "unconfirmed") {
      rows.push({ key, state: "held", seq: null, why: tiers[key].why, held: disputed.has(key) ? "disagree" : "tap" });
    } else if (sync === "sent" || sync === "queued") {
      const seq = sync === "sent" ? [...s.relay.log].reverse().find((l) => l.result === "acked" && l.keys.includes(key))?.seq ?? null : null;
      rows.push({ key, state: sync, seq, why: tiers[key].why, held: null });
    }
  }
  return rows;
}
export function queuedCount(s: Snapshot): number {
  return Object.values(s.relay.sync).filter((v) => v === "queued").length;
}
/** The "reconciled" line shows only when everything confirmed has been acknowledged over a good link (§3.1.9). */
export function reconciled(s: Snapshot): boolean {
  const r = s.relay;
  return r.link === "good" && r.pending.length === 0 && Object.values(r.sync).every((v) => v === "sent")
    && r.log.some((l) => l.tier === "full" && l.result === "acked");
}

// ---------- patient picture groups (§3.1.9) ----------
export const GROUPS: [string, (key: string) => boolean][] = [
  ["Patient", (k) => k.startsWith("patient.") || k === "complaint.chief"],
  ["History", (k) => k.startsWith("stroke.") || k.startsWith("symptom.") || k === "code_status"],
  ["Vitals", (k) => k.startsWith("vitals.")],
  ["Exam", (k) => k.startsWith("exam.") || k.startsWith("ecg.")],
  ["Meds & allergies", (k) => k.startsWith("meds.") || k === "allergies"],
  ["Transport", (k) => k.startsWith("transport.")],
  ["Scene", (k) => k.startsWith("scene.")],
];
export function groupFacts(facts: FactView[]): [string, FactView[]][] {
  const out: [string, FactView[]][] = GROUPS.map(([name]) => [name, []]);
  const other: FactView[] = [];
  for (const f of facts) {
    const i = GROUPS.findIndex(([, match]) => match(f.key));
    (i >= 0 ? out[i][1] : other).push(f);
  }
  if (other.length) out.push(["Other", other]);
  return out.filter(([, fs]) => fs.length);
}
