export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const formatValue = (value) => value === true ? "yes" : value === false ? "no" : value === null ? "unknown" : Array.isArray(value) ? value.map(formatValue).join(" · ") || "none reported" : typeof value === "object" ? Object.entries(value).map(([key, v]) => `${key}: ${formatValue(v)}`).join(" · ") : String(value);
export const newestPatient = (incidents) => Object.keys(incidents).sort((a, b) => incidents[b].first_at.localeCompare(incidents[a].first_at))[0];
export const isNewField = (field, previousSequence) => field.seq > previousSequence;
export const fieldKeys = (incident) => Object.keys(incident.fields);
/** "13:04" -> "1 h 12 m" elapsed since that wall-clock time (yesterday's if it is still ahead of now); null when the value is not a valid HH:MM. */
export const clockElapsed = (value, nowMs = Date.now()) => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(value ?? "").trim());
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  const then = new Date(nowMs);
  then.setHours(Number(m[1]), Number(m[2]), 0, 0);
  let ms = nowMs - then.getTime();
  if (ms < 0) ms += 24 * 60 * 60 * 1000;
  const minutes = Math.floor(ms / 60000);
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} m` : `${minutes} m`;
};
