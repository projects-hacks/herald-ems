// Pure functions for the hand over moment: who the patient is, where they are going, what the ED has, and whether
// the handover is close. Tested in src/test/handover.test.tsx.
import { clockSeconds, factValue, hhmm, patientLabel } from "./format";
import { activeSync, queuedCount } from "./selectors";
import type { Snapshot } from "./types";

export type StatusTone = "ok" | "low" | "medium" | "neutral";
export interface HandoverStatus { tone: StatusTone; text: string }

const confirmed = (s: Snapshot, key: string) => (s.facts[key]?.status === "confirmed" ? s.facts[key] : undefined);

/** Where the patient is handed over: once handed over, who took them (the server records it); before, the authorized
 * receiving ED, else the confirmed destination, else unknown. */
export function handoverDestination(s: Snapshot): string | null {
  if (s.incident.handed_over_to) return s.incident.handed_over_to;
  const dest = confirmed(s, "transport.destination");
  return s.relay.authorized?.destination ?? (dest ? factValue(dest) : null);
}

/** Identity, age and sex from confirmed facts only; the crew's label when none is confirmed. */
export function patientIdentity(s: Snapshot): string {
  const who = confirmed(s, "patient.name") ?? confirmed(s, "patient.identifier");
  const age = confirmed(s, "patient.age"), sex = confirmed(s, "patient.sex");
  const ageText = age ? (age.unit ? factValue(age) : `${factValue(age)} y`) : null;
  return [who ? factValue(who) : patientLabel(s), ageText, sex ? factValue(sex) : null].filter(Boolean).join(" · ");
}

/** Seconds until arrival: the running ETA clock, else a stated ETA in minutes; null when no ETA was given. */
export function etaSeconds(s: Snapshot, lastStateAt: number, nowMs: number): number | null {
  const clock = s.clocks.find((c) => c.id === "eta");
  if (clock) return clockSeconds(clock, lastStateAt, nowMs);
  const eta = s.facts["transport.eta_min"];
  return eta && typeof eta.value === "number" ? eta.value * 60 : null;
}

/** The handover is close: the crew recorded arrival, or the ETA is five minutes or less. */
export function handoverDue(s: Snapshot, lastStateAt: number, nowMs: number): boolean {
  if (s.incident.arrived_at) return true;
  const left = etaSeconds(s, lastStateAt, nowMs);
  return left !== null && left <= 300;
}

/** The one status line for the pre-alert before handover: sent and delivered, waiting for the link, or not sent. */
export function preAlertStatus(s: Snapshot): HandoverStatus {
  const r = s.relay;
  if (!r.configured) return { tone: "neutral", text: "No receiving link · the report stays on this vehicle" };
  if (!r.authorized) return { tone: "medium", text: "Pre-alert not sent" };
  const queued = queuedCount(s);
  if (queued > 0) return { tone: "low", text: `${queued} ${queued === 1 ? "update" : "updates"} waiting for the link` };
  const sent = Object.values(activeSync(s)).some((v) => v === "sent");
  const ack = r.clinician_acknowledgements?.[s.active_patient ?? s.incident.id]?.at(-1);
  const parts = ["Pre-alert live", sent ? "all confirmed updates delivered" : "nothing confirmed to send yet"];
  if (ack) parts.push(`ED acknowledged ${hhmm(ack.at)}`);
  return { tone: sent ? "ok" : "neutral", text: parts.join(" · ") };
}

/** After handover: did the final report reach the ED, and did a person there receive it. */
export function handoverDelivery(s: Snapshot): HandoverStatus {
  const r = s.relay, h = r.handover;
  if (h?.received_at) return { tone: "ok", text: `ED received ✓ ${hhmm(h.received_at)}` };
  if (h?.delivered_at) return { tone: "low", text: "Final report delivered, waiting for the ED" };
  if (!r.configured) return { tone: "neutral", text: "No receiving link · the report stays on this vehicle" };
  if (!r.authorized) return { tone: "neutral", text: "ED sharing was not authorized · the report stays on this vehicle" };
  return { tone: "low", text: "Final report waiting for the link" };
}
