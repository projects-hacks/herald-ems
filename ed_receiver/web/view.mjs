export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const formatValue = (value) => value === true ? "yes" : value === false ? "no" : value === null ? "unknown" : Array.isArray(value) ? value.map(formatValue).join(" · ") || "none reported" : typeof value === "object" ? Object.entries(value).map(([key, v]) => `${key}: ${formatValue(v)}`).join(" · ") : String(value);
export const newestPatient = (incidents) => Object.keys(incidents).sort((a, b) => incidents[b].first_at.localeCompare(incidents[a].first_at))[0];
export const isNewField = (field, previousSequence) => field.seq > previousSequence;
export const fieldKeys = (incident) => Object.keys(incident.fields);
