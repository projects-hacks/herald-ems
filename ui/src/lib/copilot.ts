// What the copilot screen shows, as pure functions of the snapshot. Two questions only:
// what Herald needs from the medic, and what Herald did on its own. Tested in src/test/copilot.test.ts.
import { allFacts } from "./selectors";
import { UNIDENTIFIED_SPEAKER, factValue, formatValue } from "./format";
import type { CaptureGroup, FactStatus, FactView, Health, Snapshot, TranscriptEntry } from "./types";

// ---------- the activity feed: clinical outcomes of what Herald did, never telemetry ----------
export type ActivityKind = "heard" | "read" | "checked" | "found" | "sent";
export interface ActivityLine { id: string; ts: string; kind: ActivityKind; text: string; detail?: string }

const SHORT: Record<string, string> = {
  "vitals.hr": "HR", "vitals.sbp": "SBP", "vitals.dbp": "DBP", "vitals.spo2": "SpO₂", "vitals.rr": "RR",
  "vitals.temp": "Temp", "vitals.glucose": "Glucose", "vitals.etco2": "EtCO₂",
};
const fromCamera = (f: FactView) => f.captured_by === "camera" || f.captured_by === "device" || f.role === "photo" || f.role === "device";
const clip = (text: string, n = 90) => (text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text);

/** "HR 112 · BP 168/94 · SpO₂ 93": one monitor reading as a clinician writes it, blood pressure paired. */
export function readingText(facts: FactView[]): string {
  const by = new Map(facts.map((f) => [f.key, f]));
  const parts: string[] = [];
  const sbp = by.get("vitals.sbp"), dbp = by.get("vitals.dbp");
  const order = Object.keys(SHORT);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  for (const f of [...facts].sort((a, b) => rank(a.key) - rank(b.key))) {
    if (f.key === "vitals.dbp" && sbp) continue;
    if (f.key === "vitals.sbp") { parts.push(`BP ${formatValue(f.value)}${dbp ? `/${formatValue(dbp.value)}` : ""}`); continue; }
    parts.push(`${SHORT[f.key] ?? f.label} ${formatValue(f.value, SHORT[f.key] ? null : f.unit)}`);
  }
  return parts.join(" · ");
}

function readKey(f: FactView): string {
  return f.provenance?.frame_id ?? f.provenance?.photo_id ?? `t:${f.ts.slice(0, 19)}`;
}

/** Words that mattered: the model took facts from them, or they asked for a county protocol. Everything else (chatter,
 *  noise that got past the filters) stays in the transcript and the record, never in the live view or the feed. */
export function relevant(s: Snapshot, t: TranscriptEntry): boolean {
  if ((t.trace?.model?.facts?.length ?? 0) > 0) return true;
  const words = t.text?.toLowerCase() ?? "";
  return (s.protocol_cues ?? []).some((c) => c.asked && !!c.query && words.includes(c.query.toLowerCase()));
}
/** How many finished utterances Herald set aside as holding nothing clinical. */
export function setAside(s: Snapshot): number {
  return s.transcripts.filter((t) => spoken(t) && t.trace?.model?.status === "done" && !relevant(s, t)).length;
}

/** Newest first. Built only from data the vehicle already records: transcripts (heard), camera/photo facts (read),
 *  label verification (checked) and acknowledged relay packets (sent). */
export function activity(s: Snapshot, limit = 6, label: (key: string) => string = (k) => SHORT[k] ?? k.split(".").at(-1)!.replace(/_/g, " ")): ActivityLine[] {
  const lines: ActivityLine[] = [];
  for (const t of s.transcripts) {
    if (t.captured_by === "camera" || t.captured_by === "device" || !t.text?.trim() || t.trace?.model?.status === "error" || !relevant(s, t)) continue;
    const who = speakerOf(t);
    const got = [...new Set((t.trace?.model?.facts ?? []).map((f) => f.label))];
    lines.push({ id: `h:${t.id}`, ts: t.ts, kind: "heard", text: `Heard ${who ? `${who}: ` : ""}“${clip(t.text.trim())}”`,
      detail: got.length ? `→ ${got.slice(0, 3).join(", ")}${got.length > 3 ? ` +${got.length - 3}` : ""}` : undefined });
  }
  const reads = new Map<string, FactView[]>();
  for (const f of allFacts(s)) {
    if (f.status === "rejected" || !fromCamera(f)) continue;
    if (f.verify) {
      const ok = f.verify.status === "match";
      lines.push({ id: `c:${f.id}`, ts: f.ts, kind: "checked",
        text: ok ? `Checked the label — ${f.verify.label_drug} matches what was said` : `Checked the label — reads ${f.verify.label_drug}, not what was said` });
      continue;
    }
    const k = readKey(f);
    reads.set(k, [...(reads.get(k) ?? []), f]);
  }
  for (const [k, facts] of reads) {
    const vitals = facts.filter((f) => f.key.startsWith("vitals."));
    const ts = facts.map((f) => f.provenance?.observed_at ?? f.ts).sort().at(-1)!;
    const what = vitals.length ? `Read the monitor — ${readingText(vitals)}` : `Read a photo — ${facts.map((f) => `${f.label} ${factValue(f)}`).join(", ")}`;
    lines.push({ id: `r:${k}`, ts, kind: "read", text: clip(what, 110) });
  }
  for (const c of s.protocol_cues ?? []) {
    const p = c.passages[0];
    if (c.state !== "found" || !p || !c.found_at) continue;
    lines.push({ id: `f:${c.id}`, ts: c.found_at, kind: "found", text: `Found Policy ${p.doc} §${p.section} for ${c.asked ? `“${c.query}”` : c.title.toLowerCase()}` });
  }
  // A relay packet re-sends the whole picture; the feed names only what reached the ED for the first time.
  const dest = s.relay.authorized?.destination ?? "the ED";
  const delivered = new Set<string>();
  const packets = [...(s.relay.log ?? [])].sort((a, b) => a.ts.localeCompare(b.ts));
  for (const p of packets) {
    if (p.result !== "acked" || (p.patient && p.patient !== (s.active_patient ?? s.incident.id))) continue;
    const fresh = p.keys.filter((k) => !delivered.has(k));
    fresh.forEach((k) => delivered.add(k));
    if (!fresh.length) continue;
    const names = fresh.slice(0, 3).map(label).join(", ") + (fresh.length > 3 ? ` +${fresh.length - 3} more` : "");
    lines.push({ id: `s:${p.seq}:${p.ts}`, ts: p.ts, kind: "sent", text: `Sent ${names} to ${dest} — delivered` });
  }
  return lines.sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, limit);
}

// ---------- live: the last thing Herald heard, and what it took from it ----------
/** Who spoke, when it is known: nothing for the medic (the default voice) or an unidentified ambient speaker. */
export function speakerOf(t: Pick<TranscriptEntry, "speaker">): string | null {
  const who = t.speaker?.trim();
  // the older ambient label ("Ambient audio · speaker unverified") still sits in restored calls
  return !who || who === "medic" || who === UNIDENTIFIED_SPEAKER || /speaker unverified/i.test(who) ? null : who;
}
export interface LiveChip { id: string; label: string; value: string; status: FactStatus }
export interface LiveHeard { id: string; ts: string; text: string; who: string | null; working: boolean; chips: LiveChip[]; effects: string[]; segments: Segment[] }
const spoken = (t: TranscriptEntry) => t.captured_by !== "camera" && t.captured_by !== "device" && !!t.text?.trim() && t.trace?.model?.status !== "error";
/** The newest words Herald heard, the facts the model took from them (with their status now) and what they changed:
 *  a checklist that moved, a new finding, a score. The extracted values are marked in the words they came from. */
export function liveHeard(s: Snapshot): LiveHeard | null {
  const t = [...s.transcripts].reverse().find((x) => spoken(x) && (x.trace?.model?.status === "running" || relevant(s, x)));
  if (!t) return null;
  const now = new Map(allFacts(s).map((f) => [f.id, f]));
  const chips = (t.trace?.model?.facts ?? []).map((f) => {
    const cur = now.get(f.id);
    return { id: f.id, label: f.label, value: factValue({ value: cur?.value ?? f.value, unit: cur?.unit ?? null }), status: cur?.status ?? f.status };
  }).filter((c) => c.status !== "rejected");
  const e = t.trace?.effects;
  const effects = [
    ...(e?.readiness ?? []).filter((r) => r.to > r.from).map((r) => (r.ready ? `${r.label} ready` : `${r.label} ${r.to} of ${r.total}`)),
    ...(e?.alerts_new ?? []).map((a) => a.label),
    ...(e?.scores ?? []).filter((x) => x.to !== x.from).map((x) => `${x.name} ${x.to}`),
  ];
  const values = (t.trace?.model?.facts ?? []).flatMap((f) => (Array.isArray(f.value) ? f.value : [f.value])).map(String).filter((v) => v.length > 1);
  return { id: t.id, ts: t.ts, text: t.text.trim(), who: speakerOf(t), working: t.trace?.model?.status === "running", chips, effects,
    segments: markWords(t.text.trim(), values) };
}
/** Marks each value where it occurs in the words, ignoring case: the words stay exactly as heard. */
export function markWords(text: string, values: string[]): Segment[] {
  const lower = text.toLowerCase();
  const spans: [number, number][] = [];
  for (const v of values) { const i = lower.indexOf(v.toLowerCase()); if (i >= 0) spans.push([i, i + v.length]); }
  spans.sort((a, b) => a[0] - b[0]);
  const out: Segment[] = []; let i = 0;
  for (const [a, b] of spans) { if (a < i) continue; if (a > i) out.push({ t: text.slice(i, a) }); out.push({ t: text.slice(a, b), hl: true }); i = b; }
  if (i < text.length) out.push({ t: text.slice(i) });
  return out;
}

// ---------- one-tap monitor readings ----------
export interface ReadingCard { frameId: string; ts: string; text: string; batchIds: string[]; individual: CaptureGroup["individual"] }
export function readingCards(s: Snapshot): ReadingCard[] {
  const facts = new Map(allFacts(s).map((f) => [f.id, f]));
  return (s.capture_groups ?? []).filter((g) => g.batch_fact_ids.length).map((g) => {
    const batch = g.batch_fact_ids.map((id) => facts.get(id)).filter((f): f is FactView => !!f);
    return { frameId: g.frame_id, ts: g.ts, text: readingText(batch), batchIds: g.batch_fact_ids, individual: g.individual };
  }).filter((c) => c.text).reverse();
}
/** Facts already offered as part of a one-tap reading; the per-fact list leaves them out so nothing is asked twice. */
export function batchedIds(s: Snapshot): Set<string> {
  return new Set((s.capture_groups ?? []).flatMap((g) => g.batch_fact_ids));
}

// ---------- presence: the whole system status in one pill ----------
export type PresenceTone = "ok" | "idle" | "down" | "replay";
export interface Presence { tone: PresenceTone; text: string }
export function presence(o: {
  replay: boolean; offline: boolean; hasSnapshot: boolean; health: Health | null;
  listening: boolean; micError: string | null; monitorWatching: boolean; cameraError: string | null;
}): Presence {
  if (o.replay) return { tone: "replay", text: "Demo replay · recorded scenario" };
  if (o.offline) return { tone: "down", text: o.hasSnapshot ? "Offline — vehicle server disconnected, showing last state" : "Connecting to the vehicle…" };
  if (o.health?.llm_available === false) return { tone: "down", text: "Speech is not becoming facts right now — words are kept; enter key facts by hand" };
  if (o.micError) return { tone: "down", text: /https|localhost|secure/i.test(o.micError) ? "Microphone blocked by the browser — open Herald via localhost" : `Microphone stopped — ${o.micError}` };
  if (o.cameraError) return { tone: "down", text: `Camera stopped — ${o.cameraError}` };
  const doing = [o.listening && "Listening", o.monitorWatching && "watching the monitor"].filter(Boolean) as string[];
  if (!doing.length) return { tone: "idle", text: "Not listening" };
  const text = doing.join(" · ");
  return { tone: "ok", text: text.charAt(0).toUpperCase() + text.slice(1) };
}

// ---------- the patient line ----------
/** "68 M · Stroke alert · ETA 12 min → Regional CSC", from confirmed facts only; unknown parts are left out. */
export function patientLine(s: Snapshot): string {
  const f = (k: string) => (s.facts[k]?.status === "confirmed" ? s.facts[k] : undefined);
  // the summary names the complaint once it is heard; until then the dispatch says why the crew is here
  const summary = s.summary || "";
  const parts = [summary && summary.includes(" · ") ? summary
    : [summary, s.incident.dispatch].filter(Boolean).join(" · ") || "New patient"];
  const dest = f("transport.destination");   // the ETA counts down in the situation bar; one ETA on screen, not two
  if (dest) parts[parts.length - 1] += ` → ${factValue(dest)}`;
  return parts.join(" · ");
}

// ---------- what the ED has ----------
export interface EdHas { destination: string | null; sent: string[]; waiting: number; lastAck: string | null; authorized: boolean; configured: boolean }
export function edHas(s: Snapshot, label: (key: string) => string): EdHas {
  const sync = s.relay.patients?.[s.active_patient ?? s.incident.id]?.sync ?? s.relay.sync ?? {};
  return {
    destination: s.relay.authorized?.destination ?? null,
    sent: Object.entries(sync).filter(([, v]) => v === "sent").map(([k]) => label(k)),
    waiting: allFacts(s).filter((f) => f.status === "unconfirmed").length,
    lastAck: s.relay.last_ack_at, authorized: !!s.relay.authorized, configured: s.relay.configured,
  };
}

// ---------- what Herald knows about the patient ----------
/** Whatever has been heard or read, grouped; the fields exist because they were said, not because a form has them.
 *  Vitals are left to the monitor and the movement strip; the safety keys lead. */
export const SAFETY_KEYS = ["allergies", "meds.anticoagulant", "code_status"];
const HIDE = (k: string) => k.startsWith("vitals.") || k.startsWith("score.") || k.startsWith("exam.") || k === "transport.eta_min"
  || k === "transport.destination" || k === "meds.list";   // exam items add up into the scores; the medication list repeats the anticoagulant
export interface KnownGroup { name: string; facts: FactView[] }
export function patientKnown(s: Snapshot, groups: [string, (key: string) => boolean][]): KnownGroup[] {
  const facts = Object.values(s.facts).filter((f) => f.status === "confirmed" && !HIDE(f.key));   // unconfirmed ones wait in Needs you
  const safety = SAFETY_KEYS.map((k) => facts.find((f) => f.key === k)).filter((f): f is FactView => !!f);
  const rest = facts.filter((f) => !SAFETY_KEYS.includes(f.key));
  const out: KnownGroup[] = safety.length ? [{ name: "Safety", facts: safety }] : [];
  for (const [name, test] of groups) {
    const g = rest.filter((f) => test(f.key)).sort((a, b) => a.ts.localeCompare(b.ts));
    if (g.length) out.push({ name, facts: g });
  }
  const other = rest.filter((f) => !groups.some(([, test]) => test(f.key)));
  if (other.length) out.push({ name: "Other", facts: other });
  return out;
}

// ---------- county passages as a quick view ----------
/** The county's own sentences, never a model's paraphrase: each chosen passage is cut into sentences, its section
 *  numbering dropped, and the shortest sentences that carry the passage's substance kept. Highlighting is plain
 *  pattern matching (numbers with units and time windows, facility names, the words that were asked). */
export interface Segment { t: string; hl?: boolean }
export interface KeyPoint { segments: Segment[]; cite: string }

const UNIT = String.raw`(?:mg|mcg|g|mL|ml|L|mmHg|%|minutes?|mins?|hours?|hrs?|seconds?|days?|years?|kg|joules?|J|bpm)`;
const HL = [
  new RegExp(String.raw`\b(?:[a-z-]+\s)?\(?\d+(?:\.\d+)?\)?\s*${UNIT}\b`, "gi"),           // "forty-five (45) minutes", "324 mg"
  /\b(?:Comprehensive|Primary|Thrombectomy-Capable)\s+Stroke\s+Center\b|\bSTEMI\s+(?:Receiving\s+)?Center\b|\bTrauma\s+Center\b|\b(?:Level\s+[IVX]+)\b/gi,
];
/** Only what a medic scans for: numbers with their units and time windows, and destination facilities. Marking every
 *  word of the question would mark everything, which marks nothing. */
export function highlight(text: string, exact: string[] = []): Segment[] {
  const phrases = exact.filter((m) => m && text.includes(m)).map((m) => new RegExp(m.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"));
  const patterns = [...HL, ...phrases];
  const marks: [number, number][] = [];
  for (const re of patterns) for (const m of text.matchAll(re)) marks.push([m.index!, m.index! + m[0].length]);
  marks.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [s, e] of marks) { const last = merged.at(-1); if (last && s <= last[1]) last[1] = Math.max(last[1], e); else merged.push([s, e]); }
  const out: Segment[] = []; let i = 0;
  for (const [s, e] of merged) { if (s > i) out.push({ t: text.slice(i, s) }); out.push({ t: text.slice(s, e), hl: true }); i = e; }
  if (i < text.length) out.push({ t: text.slice(i) });
  return out;
}
export function keyPoints(passages: { doc: string; section: string; text: string }[], max = 2, skip: Set<string> = new Set()): KeyPoint[] {
  const out: KeyPoint[] = [];
  for (const p of passages) {
    const cite = `${p.doc} §${p.section}`;
    if (skip.has(cite)) continue;                         // already shown under another situation
    skip.add(cite);
    const body = p.text.replace(/^\s*[\d.]+[.)]?\s+/, "").replace(/^[A-Z]\.\s+/, "").trim();
    const sentences = body.split(/(?<=[.;])\s+(?=[A-Z(])/).map((s) => s.trim()).filter((s) => s.length > 12);
    let lead = sentences[0] ?? body;
    if (lead.endsWith(":")) lead = body.slice(0, 260);    // "shall be transported to:" means nothing without what follows
    if (lead.trimEnd().endsWith(":")) continue;            // ...and if nothing follows in this passage, it is not a key point
    const text = lead.length > 240 ? `${lead.slice(0, 237).replace(/\s+\S*$/, "")} …` : lead;
    out.push({ segments: highlight(text), cite });
    if (out.length >= max) break;
  }
  return out;
}

/** The model's picks when it made them (each already verified server-side to be the county's words), otherwise the
 *  lead sentence of each passage. Either way a passage shows once across situations. */
export function cuePoints(c: { passages: { doc: string; section: string; text: string }[]; points?: { text: string; cite: string; marks: string[] }[] },
  skip: Set<string>): KeyPoint[] {
  if (!c.points) return keyPoints(c.passages, 2, skip);   // the model could not be asked: each passage's lead sentence
  // an empty list is the model's judgement that these passages hold no rule for this situation: show none
  const out: KeyPoint[] = [];
  for (const p of c.points) {
    const key = `${p.cite}|${p.text}`;
    if (skip.has(key)) continue;
    skip.add(key); skip.add(p.cite);
    out.push({ segments: highlight(p.text, p.marks), cite: p.cite });
  }
  return out;
}
