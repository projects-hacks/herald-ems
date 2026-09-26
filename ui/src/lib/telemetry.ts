// What this box spent on the call's AI (GET /api/telemetry): tokens, GPU power and energy, and what the same work would
// cost in the cloud. Pure functions of the endpoint's reply; every field may be missing or null. Tested in
// src/test/telemetry.test.tsx.
import type { Telemetry, TelemetryRequest } from "./types";

/** Fetches the telemetry once; null when the box does not answer within `timeoutMs` or `signal` aborts. */
export async function fetchTelemetry(signal?: AbortSignal, timeoutMs = 4000): Promise<Telemetry | null> {
  const abort = new AbortController();
  const stop = () => abort.abort();
  const timer = setTimeout(stop, timeoutMs);
  signal?.addEventListener("abort", stop);
  try {
    const r = await fetch("/api/telemetry", { signal: abort.signal });
    const t = r.ok ? ((await r.json()) as Telemetry) : null;
    return t && typeof t === "object" ? t : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}

export const KIND_LABEL: Record<string, string> = { stt: "Speech to text", text: "Text model", vision: "Vision" };

export interface EnergyPerCall { kind: string; label: string; calls: number; measured: number; joules: number | null; watts: number | null }

/** Energy per call by kind over the recent requests. The GPU power is sampled, so a call shorter than the sampling
 *  step can read 0 J: the means are over the calls that were measured (energy above 0), the average power is their
 *  energy over their time (a long call weighs more than a short one), and both are null when none was measured. */
export function energyPerCall(recent: TelemetryRequest[] | null | undefined): EnergyPerCall[] {
  const by = new Map<string, TelemetryRequest[]>();
  for (const r of recent ?? []) if (r && typeof r.kind === "string") by.set(r.kind, [...(by.get(r.kind) ?? []), r]);
  const order = Object.keys(KIND_LABEL);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  return [...by.entries()].sort(([a], [b]) => rank(a) - rank(b)).map(([kind, rows]) => {
    const measured = rows.filter((r) => (r.energy_j ?? 0) > 0);
    const joules = measured.reduce((sum, r) => sum + r.energy_j!, 0);
    const seconds = measured.reduce((sum, r) => sum + (r.duration_s ?? 0), 0);
    return { kind, label: KIND_LABEL[kind] ?? kind, calls: rows.length, measured: measured.length,
      joules: measured.length ? joules / measured.length : null, watts: seconds > 0 ? joules / seconds : null };
  });
}

const isNum = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
// numbers only, grouped the same everywhere (en-US); clock times go through lib/format's 24 h helpers
const decimals = (n: number, digits: number) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);

/** A number with a fixed number of decimals and its unit; a dash when the box did not report it. */
export function fmt(n: number | null | undefined, digits = 0, unit = ""): string {
  if (!isNum(n)) return "—";
  const text = decimals(n, digits);
  return unit ? `${text} ${unit}` : text;
}

/** Dollars with enough decimals to show a fraction of a cent. */
export function usd(n: number | null | undefined): string {
  if (!isNum(n)) return "—";
  return `$${decimals(n, n !== 0 && Math.abs(n) < 0.1 ? 4 : 2)}`;
}

/** "4 h 20 min", "12 min", "40 s": how long the box has been counting. */
export function duration(seconds: number | null | undefined): string | null {
  if (!isNum(seconds) || seconds < 0) return null;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const h = Math.floor(seconds / 3600), m = Math.round((seconds % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}
