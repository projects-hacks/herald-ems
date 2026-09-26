// POST helpers with pending/error state (§5.7): the button disables within 0.1 s, a request times out
// after 5 s with an inline error, and success stays "pending" until the next snapshot shows it (no optimistic updates).
// In fixture mode every action is off.
import { authHeaders } from "./authToken";
import { useHerald } from "./store";
import type { HandoffReportData } from "./types";

export async function act(key: string, url: string, body?: unknown, failCopy = "The Herald server didn't answer. Try again.") {
  return (await send(key, url, body, failCopy, false)).ok;
}

/** Like act(), for an endpoint whose reply the screen needs (POST /api/handoff/not-obtained returns the report).
 *  null when the action was not sent or failed; the failure shows under the button like any other action. */
export async function actJson<T>(key: string, url: string, body?: unknown, failCopy = "The Herald server didn't answer. Try again."): Promise<T | null> {
  const r = await send(key, url, body, failCopy, true);
  return r.ok ? (r.data as T) : null;
}

async function send(key: string, url: string, body: unknown, failCopy: string, readReply: boolean): Promise<{ ok: boolean; data?: unknown }> {
  const st = useHerald.getState();
  if (st.source === "fixture" || st.stale || st.conn !== "open") {
    st.showToast(st.source === "fixture" ? "Replay: actions are off" : "Vehicle connection unavailable. Action not sent.");
    return { ok: false };
  }
  if (st.pending[key] === "pending" || st.pending[key] === "sent") return { ok: false };   // one request per double tap
  useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: "pending" } });
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "X-Herald-Patient": st.snapshot?.incident.id ?? "", ...authHeaders(),
                ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error(String(r.status));
    const data = readReply ? await r.json() : undefined;
    // The broadcast can arrive before the HTTP response. Re-fetch once so a successful
    // action never waits forever for a snapshot that already arrived.
    const state = await fetch("/api/state", { signal: AbortSignal.timeout(5000) });
    if (!state.ok) throw new Error(String(state.status));
    useHerald.getState().setSnapshot(await state.json());
    const pending = { ...useHerald.getState().pending };
    delete pending[key];
    useHerald.setState({ pending });
    return { ok: true, data };
  } catch {
    useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: { error: failCopy } } });
    return { ok: false };
  }
}

export const api = {
  resumeEncounter: () => act("encounter:resume", "/api/encounters/resume"),
  encounterAction: (action: "arrive" | "transfer" | "finish") => act(`encounter:${action}`, `/api/encounters/current/${action}`),
  activatePatient: (id: string) => act(`patient:${id}`, `/api/patients/${encodeURIComponent(id)}/activate`),
  addPatient: (label: string) => act("patient:add", "/api/patients", { label }),
  confirm: (factId: string) => act(`confirm:${factId}`, `/api/facts/${factId}/confirm`, undefined, "Couldn't confirm. The Herald server didn't answer. Try again."),
  confirmMany: (ids: string[]) => act(`confirm-many:${ids.slice().sort().join(",")}`, "/api/facts/confirm", { ids }, "Couldn't confirm these readings. Review them and try again."),
  confirmReading: (frameId: string) => act(`reading:${frameId}`, `/api/readings/${encodeURIComponent(frameId)}/confirm`, undefined,
    "Couldn't confirm this reading. Review the values and try again."),
  reject: (factId: string) => act(`reject:${factId}`, `/api/facts/${factId}/reject`, undefined, "Couldn't reject. The Herald server didn't answer. Try again."),
  correct: (factId: string, value: unknown) => act(`correct:${factId}`, `/api/facts/${factId}/correct`, { value }, "Couldn't save the correction. Check the value and try again."),
  // A medic tapping a criterion the model never heard: the same generic structured-fact endpoint every manual
  // entry uses (ManualEntry), so it starts unconfirmed like any other structured reading and needs the usual tap
  // to confirm. No new write path.
  // The NEWS2 SpO2 target switch (1 = 94-98%, 2 = 88-92% hypercapnic). One tap, written confirmed: the medic's tap is
  // the clinician direction RCP requires for Scale 2. Audited server-side; switching back is the same tap.
  setSpo2Scale: (scale: 1 | 2) => act(`spo2-scale:${scale}`, "/api/patient/spo2-scale", { scale },
    "Couldn't change the SpO2 target. The Herald server didn't answer. Try again."),
  markCriterion: (key: string, value: string) => act(`mark:${key}:${value}`, "/api/facts",
    [{ key, value: [value], unit: null }], "Couldn't record that. The Herald server didn't answer. Try again."),
  retryTranscript: (entryId: string) => act(`retry:${entryId}`, `/api/transcripts/${encodeURIComponent(entryId)}/retry`, undefined,
    "Couldn't retry these preserved words. Check that the local extractor is available."),
  authorize: (destination: string) => act("authorize", "/api/relay/authorize", { destination },
    "Couldn't authorize. The Herald server didn't answer. Try again."),
  netem: (mode: "good" | "weak" | "down") => act(`netem:${mode}`, `/api/netem/${mode}`),
  endIncident: () => act("end-incident", "/api/incident/end", undefined,
    "Couldn't end the call. Media has not been confirmed deleted; try again."),
  newIncident: (dispatch: string | null) => act("incident", "/api/incident", { dispatch }),
  // Hand over: one step that records transfer of care, sends the final confirmed report, stops capture and deletes
  // this patient's audio and photos (the server does all of it; docs/API_CONTRACT.md).
  handover: (destination: string | null) => act("handover", "/api/encounters/current/handover", { destination },
    "Couldn't hand over. Nothing was changed; check the connection and try again."),
  /** A required item the crew could not obtain (on: true), or undo that (on: false). Replies with the report. */
  notObtained: (key: string, on: boolean) => actJson<HandoffReportData>(`not-obtained:${key}`, "/api/handoff/not-obtained", { key, on },
    "Couldn't save that. The Herald server didn't answer. Try again."),
};
