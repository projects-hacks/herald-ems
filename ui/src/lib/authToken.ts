// Device token (B7): a shared secret every mutating request presents once the deployment enables one
// (server: HERALD_DEVICE_TOKEN, herald/config/settings.py). Unset on the server = disabled, the default for
// local dev; every existing fetch call keeps working with no header at all. When a token IS configured, the
// tablet captures it once from the URL it was opened with (?token=...) and keeps it in localStorage, so the
// same built ui/dist bundle works for any deployment with no rebuild.
const STORAGE_KEY = "herald.deviceToken";

function captureFromUrl(): void {
  try {
    const token = new URLSearchParams(window.location.search).get("token");
    if (token) window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* no-op: URL or localStorage unavailable (SSR, tests, a private window that blocks storage) */
  }
}
if (typeof window !== "undefined") captureFromUrl();

/** `{}`, or the one header to spread into a mutating request's `headers` once a token is stored. */
export function authHeaders(): Record<string, string> {
  try {
    const token = window.localStorage.getItem(STORAGE_KEY);
    return token ? { "X-Herald-Token": token } : {};
  } catch {
    return {};
  }
}
