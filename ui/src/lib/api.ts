// POST helpers with pending/error state (UX_PLAN §3.0, §5.7): the button disables within 0.1 s, a request times out
// after 5 s with an inline error, and success stays "pending" until the next snapshot shows it (no optimistic updates).
// In fixture mode every action is off.
import { useHerald } from "./store";

export async function act(key: string, url: string, body?: unknown, failCopy = "The Herald server didn't answer. Try again.") {
  const st = useHerald.getState();
  if (st.source === "fixture") {
    st.showToast("Replay: actions are off");
    return false;
  }
  if (st.pending[key] === "pending" || st.pending[key] === "sent") return false;   // one request per double tap
  useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: "pending" } });
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error(String(r.status));
    useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: "sent" } });
    return true;
  } catch {
    useHerald.setState({ pending: { ...useHerald.getState().pending, [key]: { error: failCopy } } });
    return false;
  }
}

export const api = {
  confirm: (factId: string) => act(`confirm:${factId}`, `/api/facts/${factId}/confirm`, undefined, "Couldn't confirm. The Herald server didn't answer. Try again."),
  reject: (factId: string) => act(`reject:${factId}`, `/api/facts/${factId}/reject`, undefined, "Couldn't reject. The Herald server didn't answer. Try again."),
  authorize: (destination: string) => act("authorize", "/api/relay/authorize", { destination, scope: "stroke pre-alert set" },
    "Couldn't authorize. The Herald server didn't answer. Try again."),
  netem: (mode: "good" | "weak" | "down") => act(`netem:${mode}`, `/api/netem/${mode}`),
  newIncident: (dispatch: string | null) => act("incident", "/api/incident", { dispatch }),
};
