export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
/** 24-hour clock, zero-padded (clocks are HH:MM everywhere, never a locale-dependent 12-hour string). */
export const hhmm = (dateLike) => {
  const d = dateLike instanceof Date ? dateLike : new Date(dateLike);
  return Number.isNaN(d.getTime()) ? "—" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
// A zone-qualified timestamp (the route ETA's arrival time) reads as this screen's clock time.
const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;
export const formatValue = (value) => value === true ? "yes" : value === false ? "no" : value === null ? "unknown" : Array.isArray(value) ? value.map(formatValue).join(" · ") || "none reported" : typeof value === "object" ? Object.entries(value).map(([key, v]) => `${key}: ${formatValue(v)}`).join(" · ") : typeof value === "string" && ISO_INSTANT.test(value) ? hhmm(value) : String(value);
export const newestPatient = (incidents) => Object.keys(incidents).sort((a, b) => incidents[b].first_at.localeCompare(incidents[a].first_at))[0];
export const isNewField = (field, previousSequence) => field.seq > previousSequence;
export const fieldKeys = (incident) => Object.keys(incident.fields);
/** Elapsed LKW is usable only when the vehicle sent an absolute, zone-qualified timestamp. */
export const observedElapsed = (iso, nowMs = Date.now()) => {
  if (typeof iso !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(iso)) return null;
  const at = Date.parse(iso);
  if (!Number.isFinite(at) || at > nowMs) return null;
  const minutes = Math.floor((nowMs - at) / 60000);
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} m` : `${minutes} m`;
};
