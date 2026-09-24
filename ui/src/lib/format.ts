// Clocks are HH:MM:SS everywhere (Pulsara's convention, UX_PLAN §3.0); numbers never tween.
import type { FactValue, FactView } from "./types";

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
/** Seconds between an ISO time and now (positive when `iso` is in the past). */
export function secondsSince(iso: string, nowMs: number): number {
  return (nowMs - new Date(iso).getTime()) / 1000;
}

export function formatValue(v: FactValue, unit?: string | null): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
  if (typeof v === "boolean") return v ? "yes" : "no";
  return unit ? `${v} ${unit}` : String(v);
}
export function factValue(f: Pick<FactView, "value" | "unit">): string {
  return formatValue(f.value, f.unit);
}
/** "husband", "daughter", or the role when no speaker was named. */
export function sourceName(f: Pick<FactView, "speaker" | "role">): string {
  return f.speaker || f.role;
}
export function shortId(id: string): string {
  return `…${id.slice(-4)}`;
}

/** A clock's value now: the server's `seconds` at snapshot time, advanced by the time since that snapshot arrived.
 *  Works the same live and in a replay, and is immune to the laptop's clock being off. For `since` clocks it's
 *  the elapsed time; for `until` clocks (ETA, reassess) the time left (negative when overdue). */
export function clockSeconds(c: { seconds: number; since?: string; until?: string }, lastStateAt: number, nowMs: number): number {
  const drift = Math.max(0, (nowMs - lastStateAt) / 1000);
  return c.until !== undefined ? c.seconds - drift : c.seconds + drift;
}
