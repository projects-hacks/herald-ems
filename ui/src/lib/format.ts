// Clocks are HH:MM:SS everywhere (Pulsara's convention, docs/API_CONTRACT.md); numbers never tween.
import type { FactRecord, FactValue, FactView, Snapshot } from "./types";

const pad = (n: number) => String(Math.floor(n)).padStart(2, "0");

export function hhmmss(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(Math.abs(totalSeconds)));
  return `${pad(s / 3600)}:${pad((s % 3600) / 60)}:${pad(s % 60)}`;
}
export function hhmm(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export function clockTime(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function formatValue(v: FactValue, unit?: string | null): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "object") return formatRecord(v);
  return unit ? `${v} ${unit}` : String(v);
}

/** One event, as a paramedic would say it: "aspirin 324 mg PO at 14:05 · by fire · ×3"; "iv access · 18 gauge left AC". */
export function formatRecord(r: FactRecord): string {
  const what = String(r.drug ?? r.procedure ?? "");
  const dose = r.dose !== undefined ? `${r.dose}${r.unit ? ` ${r.unit}` : ""}` : "";
  const main = [what, dose, r.route, r.time !== undefined ? `at ${r.time}` : ""].filter(Boolean).join(" ");
  const extra = [r.detail, r.by && r.by !== "crew" ? `by ${r.by}` : "", Number(r.count) > 1 ? `×${r.count}` : ""].filter(Boolean);
  return [main, ...extra].join(" · ") || "—";
}
export function factValue(f: Pick<FactView, "value" | "unit">): string {
  return formatValue(f.value, f.unit);
}
/** "husband", "daughter", or the role when no speaker was named. */
export function sourceName(f: Pick<FactView, "speaker" | "role">): string {
  return f.speaker || f.role;
}

/** A crew label is context, never a substitute for confirmed patient identity. */
export function patientLabel(s: Snapshot | null | undefined): string {
  if (!s) return "Waiting for patient";
  return s.patients?.find((patient) => patient.id === (s.active_patient ?? s.incident.id))?.label || "Current patient";
}

/** A clock's value now: the server's `seconds` at snapshot time, advanced by the time since that snapshot arrived.
 *  Works the same live and in a replay, and is immune to the laptop's clock being off. For `since` clocks it's
 *  the elapsed time; for `until` clocks (ETA, reassess) the time left (negative when overdue). */
export function clockSeconds(c: { seconds: number; since?: string; until?: string }, lastStateAt: number, nowMs: number): number {
  const drift = Math.max(0, (nowMs - lastStateAt) / 1000);
  return c.until !== undefined ? c.seconds - drift : c.seconds + drift;
}
