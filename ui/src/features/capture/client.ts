import { useHerald } from "@/lib/store";

export function livePatient(): string {
  const s = useHerald.getState();
  if (s.source !== "live" || s.conn !== "open" || s.stale || !s.snapshot) throw new Error("Capture needs a live vehicle connection.");
  return s.snapshot.incident.id;
}
export async function submitCapture(path: string, body: unknown, patient: string) {
  if (livePatient() !== patient) throw new Error("Patient changed. Review before submitting again.");
  const form = body instanceof FormData;
  const response = await fetch(path, { method: "POST", headers: {
    "X-Herald-Patient": patient, ...(!form ? { "Content-Type": "application/json" } : {}) },
    body: form ? body : JSON.stringify(body), signal: AbortSignal.timeout(form ? 90000 : 15000) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `Capture not accepted (${response.status}). Check the transcript before retrying.`);
  }
  return response.json();
}
