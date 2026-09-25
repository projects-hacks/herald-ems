// POST helpers with pending/error state (docs/API_CONTRACT.md, §5.7): the button disables within 0.1 s, a request times out
// after 5 s with an inline error, and success stays "pending" until the next snapshot shows it (no optimistic updates).
// In fixture mode every action is off.
import { useHerald } from "./store";

export async function act(key: string, url: string, body?: unknown, failCopy = "The Herald server didn't answer. Try again.") {
  const st = useHerald.getState();
  if (st.source === "fixture" || st.stale || st.conn !== "open") {
    st.showToast(st.source === "fixture" ? "Replay: actions are off" : "Vehicle connection unavailable. Action not sent.");
    return false;
  }
  if (st.pending[key] === "pending" || st.pending[key] === "sent") return false;   // one request per double tap
  useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: "pending" } });
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "X-Herald-Patient": st.snapshot?.incident.id ?? "", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error(String(r.status));
    // The broadcast can arrive before the HTTP response. Re-fetch once so a successful
    // action never waits forever for a snapshot that already arrived.
    const state = await fetch("/api/state", { signal: AbortSignal.timeout(5000) });
    if (!state.ok) throw new Error(String(state.status));
    useHerald.getState().setSnapshot(await state.json());
    const pending = { ...useHerald.getState().pending };
    delete pending[key];
    useHerald.setState({ pending });
    return true;
  } catch {
    useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: { error: failCopy } } });
    return false;
  }
}

export const api = {
  activatePatient: (id: string) => act(`patient:${id}`, `/api/patients/${encodeURIComponent(id)}/activate`),
  addPatient: (label: string) => act("patient:add", "/api/patients", { label }),
  confirm: (factId: string) => act(`confirm:${factId}`, `/api/facts/${factId}/confirm`, undefined, "Couldn't confirm. The Herald server didn't answer. Try again."),
  confirmMany: (ids: string[]) => act(`confirm-many:${ids.slice().sort().join(",")}`, "/api/facts/confirm", { ids }, "Couldn't confirm these readings. Review them and try again."),
  reject: (factId: string) => act(`reject:${factId}`, `/api/facts/${factId}/reject`, undefined, "Couldn't reject. The Herald server didn't answer. Try again."),
  correct: (factId: string, value: unknown) => act(`correct:${factId}`, `/api/facts/${factId}/correct`, { value }, "Couldn't save the correction. Check the value and try again."),
  retryTranscript: (entryId: string) => act(`retry:${entryId}`, `/api/transcripts/${encodeURIComponent(entryId)}/retry`, undefined,
    "Couldn't retry these preserved words. Check that the local extractor is available."),
  authorize: (destination: string) => act("authorize", "/api/relay/authorize", { destination },
    "Couldn't authorize. The Herald server didn't answer. Try again."),
  netem: (mode: "good" | "weak" | "down") => act(`netem:${mode}`, `/api/netem/${mode}`),
  endIncident: () => act("end-incident", "/api/incident/end", undefined,
    "Couldn't end the call. Media has not been confirmed deleted; try again."),
  newIncident: (dispatch: string | null) => act("incident", "/api/incident", { dispatch }),
};
