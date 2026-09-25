import { authHeaders } from "@/lib/authToken";
import { useHerald } from "@/lib/store";

export async function captureAction(path: string, body: Record<string, unknown>) {
  const state = useHerald.getState();
  if (state.source === "fixture" || state.stale || state.conn !== "open") throw new Error("Capture controls need a live vehicle connection.");
  const incident = state.snapshot?.incident.id;
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ ...body, incident_id: incident }), signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`Request not accepted (${response.status}). Review the current patient state before retrying.`);
  const result = await response.json();
  const snapshot = await fetch("/api/state", { signal: AbortSignal.timeout(5000) });
  if (snapshot.ok) {
    const fresh = await snapshot.json();
    if (fresh.incident.id === incident && useHerald.getState().snapshot?.incident.id === incident) useHerald.getState().setSnapshot(fresh);
  }
  return result;
}
