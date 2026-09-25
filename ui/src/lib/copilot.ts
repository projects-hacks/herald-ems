// What the copilot screen shows, as pure functions of the snapshot (docs/COPILOT_SCREENS.md). Two questions only:
// what Herald needs from the medic, and what Herald did on its own. Tested in src/test/copilot.test.ts.
import { allFacts } from "./selectors";
import { factValue, formatValue } from "./format";
import type { CaptureGroup, FactView, Health, Snapshot } from "./types";

// ---------- the activity feed: clinical outcomes of what Herald did, never telemetry ----------
export type ActivityKind = "heard" | "read" | "checked" | "sent";
export interface ActivityLine { id: string; ts: string; kind: ActivityKind; text: string }

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

/** Newest first. Built only from data the vehicle already records: transcripts (heard), camera/photo facts (read),
 *  label verification (checked) and acknowledged relay packets (sent). */
export function activity(s: Snapshot, limit = 6, label: (key: string) => string = (k) => SHORT[k] ?? k.split(".").at(-1)!.replace(/_/g, " ")): ActivityLine[] {
  const lines: ActivityLine[] = [];
  for (const t of s.transcripts) {
    if (t.captured_by === "camera" || t.captured_by === "device" || !t.text?.trim() || t.trace?.model?.status === "error") continue;
    const who = t.speaker && t.speaker !== "medic" ? `${t.speaker}: ` : "";
    lines.push({ id: `h:${t.id}`, ts: t.ts, kind: "heard", text: `Heard ${who}“${clip(t.text.trim())}”` });
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
    lines.push({ id: `s:${p.seq}:${p.ts}`, ts: p.ts, kind: "sent", text: `Sent ${names} to ${dest} — received` });
  }
  return lines.sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, limit);
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
  if (o.health?.llm_available === false) return { tone: "down", text: "Extraction model down — speech is kept but not becoming facts" };
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
  const parts = [s.summary || s.incident.dispatch || "New patient"];
  const eta = f("transport.eta_min"), dest = f("transport.destination");
  if (eta || dest) parts.push([eta && `ETA ${formatValue(eta.value)} min`, dest && `→ ${factValue(dest)}`].filter(Boolean).join(" "));
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
