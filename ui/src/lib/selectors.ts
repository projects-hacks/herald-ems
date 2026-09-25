// Pure functions from the snapshot to what the screen shows. Tested in src/test/selectors.test.ts.
import type { Contract, ContractCriterion } from "./contract";
import type { Alert, CriteriaScoreDetail, FactView, Snapshot, StrokeScale, StrokeScaleId } from "./types";

// ---------- alert priority (IEC 60601-1-8 semantics, no sounds) ----------
export type Priority = "high" | "medium" | "low";
const RANK: Record<Priority, number> = { high: 0, medium: 2, low: 3 };
/** Score-positive screens (G.F.A.S.T., RACE) decide routing, so they get their own tier directly under the
 *  clinical-change (HIGH) alerts, above routine tap-confirms and other CHECK items. */
function alertRank(a: Alert): number {
  return a.type === "gfast_positive" || a.type === "race_positive" ? 1 : RANK[alertPriority(a)];
}

export function alertPriority(a: Alert): Priority {
  if (a.type === "trauma_alert_criteria") return a.level === "red" ? "high" : "medium";
  if (a.type === "news2_rise") return a.band === "high" ? "high" : a.band === "medium" || a.band === "low-medium" ? "medium" : "low";
  if (a.type === "news2_high" || a.type === "stemi_alert") return "high";
  return "medium";   // contradiction, confirm_required, race_positive, gfast_positive, significant_change
}
/** Stable identity for "Seen": type + key + value (§2.3). */
export function alertKey(a: Alert): string {
  switch (a.type) {
    case "trauma_alert_criteria": case "sepsis_prenotification": return `${a.type}:${a.level}:${a.criteria.join("|")}`;
    case "contradiction": case "confirm_required": return `${a.type}:${a.key}:${a.confirm_fact_id}`;
    case "significant_change": return `${a.type}:${a.key}:${a.series.join(",")}`;
    case "news2_rise": return `${a.type}:${a.from}->${a.to}`;
    case "news2_high": return `${a.type}:${a.score}`;
    case "race_positive": case "gfast_positive": return `${a.type}:${a.score}`;
    case "stemi_alert": return `${a.type}:${a.score}`;
    default: { const x = a as { type: string; label?: string }; return `${x.type}:${x.label ?? ""}`; }   // a score added in config
  }
}
/** The composed title the queue rows show for an alert, as plain text (the cabin banner headline reuses it). */
export function alertTitle(a: Alert): string {
  switch (a.type) {
    case "contradiction": return `${a.label}: sources disagree`;
    case "news2_rise": return `NEWS2 rose ${a.from} → ${a.to} · ${a.band} band`;
    case "news2_high": return `NEWS2 ${a.score} · high band`;
    case "stemi_alert": return "STEMI Alert criteria met";
    case "race_positive": return `RACE ${a.score} of 9: large-vessel screen positive`;
    case "gfast_positive": return `G.F.A.S.T. ${a.score} of 4: screen positive`;
    case "significant_change": return `${a.label} changed ${a.series.join(" → ")}`;
    default: return a.label;
  }
}
/** Contradictions and code-status confirmations can't be marked seen; they leave only when resolved. */
export function dismissable(a: Alert): boolean {
  return a.type !== "contradiction" && a.type !== "confirm_required";
}
/** Alert order: HIGH before MEDIUM before LOW, then the newest first by arrival on this screen (the
 *  server lists alerts by type, not time; without arrival data the later list position counts as newer). */
export function rankAlerts(alerts: Alert[], arrival: Record<string, number> = {}): Alert[] {
  return alerts.map((a, i) => ({ a, t: arrival[alertKey(a)] ?? i }))
    .sort((x, y) => alertRank(x.a) - alertRank(y.a) || y.t - x.t)
    .map((x) => x.a);
}

// ---------- needs attention (§3.1.6 and the alert slot §3.1.8, as one queue) ----------
/** Unconfirmed facts, minus those already shown in a contradiction or code-status alert; oldest first, the order
 *  they were heard. */
export function needsTap(s: Snapshot): FactView[] {
  const inAlert = new Set(s.alerts.flatMap((a) => ("facts" in a ? a.facts.map((f) => f.id) : [])));
  // Readings offered as one tap per monitor frame (snapshot.capture_groups) are not asked for again one by one.
  const batched = new Set((s.capture_groups ?? []).flatMap((g) => g.batch_fact_ids));
  return allFacts(s).filter((f) => f.status === "unconfirmed" && !batched.has(f.id) && (!inAlert.has(f.id) || (f.verify?.status === "mismatch" && !f.verify.resolution)))
    .sort((a, b) => a.ts.localeCompare(b.ts));
}

/** Everything that waits on the medic, in the order they should handle it:
 *  urgent (HIGH, until seen) · choose (sources disagree: data held on the vehicle, P10) · confirm (code status, then
 *  facts that need a tap) · review (informational findings, until seen). Seen alerts move to "acknowledged". */
export interface Attention {
  urgent: Alert[]; positiveScreens: Alert[]; choose: Alert[]; confirmAlerts: Alert[]; confirmFacts: FactView[]; review: Alert[]; acknowledged: Alert[];
  count: number;
}
export function attention(s: Snapshot, seen: Record<string, true>, arrival: Record<string, number> = {}, holdMark: number | null = null): Attention {
  // while push-to-talk is held, alerts that arrived after it was pressed wait (§3.1.8, P4)
  const shown = holdMark === null ? s.alerts : s.alerts.filter((a) => (arrival[alertKey(a)] ?? 0) <= holdMark);
  const ranked = rankAlerts(shown, arrival);
  const isSeen = (a: Alert) => dismissable(a) && !!seen[alertKey(a)];
  const open = ranked.filter((a) => !isSeen(a));
  const positiveScreen = (a: Alert) => a.type === "gfast_positive" || a.type === "race_positive";
  const out = {
    urgent: open.filter((a) => dismissable(a) && alertPriority(a) === "high"),
    positiveScreens: open.filter(positiveScreen),
    choose: open.filter((a) => a.type === "contradiction"),
    confirmAlerts: open.filter((a) => a.type === "confirm_required"),
    confirmFacts: needsTap(s),
    review: open.filter((a) => dismissable(a) && alertPriority(a) !== "high" && !positiveScreen(a)),
    acknowledged: ranked.filter(isSeen),
  };
  return { ...out, count: out.urgent.length + out.positiveScreens.length + out.choose.length + out.confirmAlerts.length + out.confirmFacts.length + out.review.length };
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
export function allFacts(s: Snapshot): FactView[] {
  return [...new Map([...Object.values(s.facts), ...Object.values(s.events ?? {}).flat()].map((f) => [f.id, f])).values()];
}
export function activeSync(s: Snapshot) {
  return (s.relay.authorized ? s.relay.patients?.[s.active_patient ?? s.incident.id]?.sync ?? s.relay.sync : undefined) ?? {};
}
export function patientPacket(s: Snapshot, patient?: string) { return !patient || patient === (s.active_patient ?? s.incident.id); }
export interface ErRow { key: string; state: ErRowState; seq: number | null; why: string; held: "tap" | "disagree" | null }

/** ED-set keys in relay-tier order, each sent / queued / held. Keys with nothing to send are omitted. */
export function erRows(s: Snapshot, c: Contract | null): ErRow[] {
  const tiers = c?.relayTiers ?? {};
  const keys = Object.keys(tiers).sort((a, b) => tiers[a].tier - tiers[b].tier);
  const disputed = new Set(s.alerts.filter((a) => a.type === "contradiction").map((a) => (a as { key: string }).key));
  const rows: ErRow[] = [];
  for (const key of keys) {
    const sync = activeSync(s)[key];
    const fact = s.facts[key];
    // Held wins: an unconfirmed newest value never counts as sent, even if an older confirmed value was
    // (e.g. the husband's "no allergies" went out; the daughter's "aspirin" is disputed and stays on the vehicle).
    if (fact && fact.status === "unconfirmed") {
      rows.push({ key, state: "held", seq: null, why: tiers[key].why, held: disputed.has(key) ? "disagree" : "tap" });
    } else if (sync === "sent" || sync === "queued") {
      const seq = sync === "sent" ? [...s.relay.log].reverse().find((l) => patientPacket(s, l.patient) && l.result === "acked" && l.keys.includes(key))?.seq ?? null : null;
      rows.push({ key, state: sync, seq, why: tiers[key].why, held: null });
    }
  }
  return rows;
}
export function queuedCount(s: Snapshot): number {
  return Object.values(activeSync(s)).filter((v) => v === "queued").length;
}
export function clinicianReceipt(s: Snapshot): string {
  const ack = s.relay.clinician_acknowledgements?.[s.active_patient ?? s.incident.id]?.at(-1);
  if (!ack) return "clinician receipt unknown";
  return ack.status === "received" ? "ED clinician recorded receipt" : "ED clinician recorded cath-lab activation";
}
/** The "reconciled" line shows only when everything confirmed has been acknowledged over a good link (§3.1.9). */
export function reconciled(s: Snapshot): boolean {
  const r = s.relay;
  return !!r.authorized && r.link === "good" && !r.pending.some((p) => patientPacket(s, p.patient)) && Object.values(activeSync(s)).every((v) => v === "sent")
    && r.log.some((l) => patientPacket(s, l.patient) && l.tier === "full" && l.result === "acked");
}
/** P3.2: the ED's own count of sequence numbers it told the vehicle it already had — never estimated from a
 * sequence gap. Older recorded fixtures may predate this field, so it is optional; absent means unknown. */
export function reconciledDuplicates(s: Snapshot): number | null {
  return typeof s.relay.duplicates_acked === "number" ? s.relay.duplicates_acked : null;
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

// ---------- field-triage / county trauma criteria checklist ----------
// Speech recall on trauma.criteria measures ~0.2: most injury-pattern/mechanism criteria a medic actually
// observes are never heard by the model, so the score must not look like an automatic screen. A criterion the
// contract marks `tap` (a plain "value described in a list key" rule) becomes a one-tap checklist item instead
// of a silent gap; everything else (vitals, medications, a recorded procedure) stays a read-only line sourced
// from its own capture flow, per the "never invent what the backend can't record" rule.
export function criteriaScore(s: Snapshot, id: string): CriteriaScoreDetail | undefined {
  return (s.scores as unknown as Record<string, CriteriaScoreDetail | undefined>)[id];
}
export interface TraumaCriterionRow {
  code: string | null; label: string; group: string;
  /** "confirmed": counts toward the score now. "unconfirmed": heard or tapped, needs one more tap to confirm.
   * "unmarked": tappable but nothing recorded yet. "computed": no tap target; state comes from the live score. */
  status: "confirmed" | "unconfirmed" | "unmarked" | "computed";
  computedState?: "met" | "not_met" | "unknown";
  factId?: string; tap?: { key: string; value: string };
}
function flattenLive(rows: import("./types").CriteriaRow[] | undefined): Map<string, import("./types").CriteriaRow> {
  const out = new Map<string, import("./types").CriteriaRow>();
  for (const r of rows ?? []) {
    if (r.code) out.set(r.code, r);
    for (const p of r.parts ?? []) if (p.code) out.set(p.code, p);
  }
  return out;
}
/** For a `tap` criterion not yet met, has the medic (or speech) already put a matching, non-rejected fact on the
 * record? Prefers a confirmed occurrence; otherwise the most recent unconfirmed one. Scans `timeline` because
 * an accumulating list key (trauma.criteria) keeps one fact per utterance/tap, not one merged fact per key. */
function matchingFact(s: Snapshot, tap: { key: string; value: string }): FactView | undefined {
  const hits = s.timeline.filter((f) => f.key === tap.key && f.status !== "rejected"
    && Array.isArray(f.value) && (f.value as string[]).some((v) => v.toLowerCase() === tap.value.toLowerCase()));
  return hits.find((f) => f.status === "confirmed") ?? hits.at(-1);
}
export function traumaCriteriaRows(s: Snapshot, contractRows: ContractCriterion[] | undefined, scoreId: string): TraumaCriterionRow[] {
  const live = flattenLive(criteriaScore(s, scoreId)?.criteria);
  return (contractRows ?? []).map((c): TraumaCriterionRow => {
    const liveState = c.code ? live.get(c.code)?.state : undefined;
    if (!c.tap) return { code: c.code, label: c.label, group: c.group, status: "computed", computedState: liveState };
    if (liveState === "met") return { code: c.code, label: c.label, group: c.group, status: "confirmed", tap: c.tap };
    const fact = matchingFact(s, c.tap);
    if (fact) return { code: c.code, label: c.label, group: c.group, status: fact.status === "confirmed" ? "confirmed" : "unconfirmed", factId: fact.id, tap: c.tap };
    return { code: c.code, label: c.label, group: c.group, status: "unmarked", tap: c.tap };
  });
}
