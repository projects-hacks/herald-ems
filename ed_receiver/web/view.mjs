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

/** The pre-alert checklists the vehicle has open, from the relayed `alert.readiness` line
 *  ("STEMI alert 3/5; Stroke alert 7/7 ready"). Anything that does not parse is left out, never guessed. */
export const openChecklists = (text) => typeof text !== 'string' ? [] : text.split(';')
  .map((part) => part.trim().match(/^(.+?) (\d+)\/(\d+)( ready)?$/)).filter(Boolean)
  .map((m) => ({ label: m[1], done: Number(m[2]), total: Number(m[3]), ready: Boolean(m[4]) }));

/** Header alert badges (config/ed_display.yaml `alerts`): shown when the vehicle's open checklist names the alert or
 *  its criteria score arrived met (anything but that score's not-met line). */
export function alertBadges(fields, alerts, keys = {}) {
  const open = openChecklists(fields['alert.readiness']?.v);
  return (alerts ?? []).flatMap((alert) => {
    const list = open.find((row) => row.label === alert.readiness_label);
    const score = alert.score ? fields[alert.score] : undefined;
    const met = score !== undefined && score.v !== keys[alert.score]?.not_met;
    if (!list && !met) return [];
    const detail = [met ? 'criteria met' : null, list ? `pre-alert ${list.done}/${list.total}${list.ready ? ' ready' : ''}` : null];
    return [{ text: alert.text, tone: alert.tone ?? 'critical', detail: detail.filter(Boolean).join(' · ') }];
  });
}

/** "62 M": the received age and sex, or null when neither arrived. */
export function ageSex(fields, header = {}) {
  const age = fields[header.age]?.v, sex = fields[header.sex]?.v;
  const short = typeof sex === 'string' && /^(male|female)$/i.test(sex) ? sex[0].toUpperCase() : sex;
  const parts = [age, short].filter((part) => part !== undefined && part !== null && part !== '');
  return parts.length ? parts.map(String).join(' ') : null;
}

const numeric = (value) => typeof value === 'number' && Number.isFinite(value);
const severityRank = { abnormal: 1, critical: 2 };

/** One vital tile from its spec ({short, keys, join}): the joined received value, the unit of the first received
 *  key, its trend as this screen received it, the worst severity, and when it last changed. */
export function vitalTile(spec, incident, keys = {}) {
  const present = spec.keys.filter((key) => incident.fields[key]);
  if (!present.length) return { short: spec.short, missing: true };
  const lead = present[0];
  const points = (incident.history?.[lead] ?? []).filter((point) => numeric(point.v));
  const previous = points.length > 1 ? points[points.length - 2] : null;
  const current = incident.fields[lead].v;
  const severity = present.map((key) => incident.severity?.[key]).filter(Boolean)
    .sort((a, b) => (severityRank[b] ?? 0) - (severityRank[a] ?? 0))[0] ?? null;
  return {
    short: spec.short, missing: false, keys: present,
    value: present.map((key) => formatValue(incident.fields[key].v)).join(spec.join ?? ' · '),
    unit: keys[lead]?.unit ?? '', severity, points: points.slice(-12),
    previous, direction: previous && numeric(current) ? Math.sign(current - previous.v) : 0,
    at: present.map((key) => incident.fields[key].t).sort().at(-1),
  };
}

/** SVG polyline points for a sparkline of numeric history, scaled into width x height (flat when constant). */
export function sparkline(points, width = 120, height = 32) {
  const values = points.map((point) => point.v).filter(numeric);
  if (values.length < 2) return '';
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const round = (n) => Math.round(n * 10) / 10;
  return values.map((v, i) => `${round((i / (values.length - 1)) * width)},${round(hi === lo ? height / 2 : height - ((v - lo) / span) * height)}`).join(' ');
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const present = (part) => part !== undefined && part !== null && part !== '';
/** Plain words for one care event record (a dose given, a procedure done), from its own received fields only. */
export function careText(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return formatValue(value);
  const dose = present(value.dose) ? `${value.dose}${value.unit ? ` ${value.unit}` : ''}` : null;
  return [value.drug ?? value.procedure, dose, value.route, value.detail, value.count > 1 ? `×${value.count}` : null,
    value.by ? `by ${value.by}` : null, value.before_arrival ? 'before EMS arrival' : null].filter(present).map(String).join(' ');
}

/** Every received care event (the latest list per care key), with the best time the data holds: the event's own
 *  recorded time, else its observed/recorded time in the full-sync history, else when this screen received it. */
export function careEvents(incident, careKeys = []) {
  const out = [];
  for (const key of careKeys) {
    const field = incident.fields[key];
    if (!field) continue;
    for (const value of Array.isArray(field.v) ? field.v : [field.v]) {
      const synced = (incident.timeline ?? []).find((point) => point.k === key && same(point.v, value));
      const firstSeen = (incident.history?.[key] ?? []).find((entry) => (Array.isArray(entry.v) ? entry.v : [entry.v]).some((v) => same(v, value)));
      const stamp = synced ? (synced.o ?? synced.t) : firstSeen?.t ?? field.t;
      const ms = Date.parse(stamp);
      const own = value && typeof value === 'object' && present(value.time) ? formatValue(value.time) : null;
      out.push({ key, value, text: careText(value), time: own ?? hhmm(stamp), source: own || synced ? 'recorded' : 'received',
        ms: Number.isFinite(ms) ? ms : Infinity, order: out.length });
    }
  }
  return out.sort((a, b) => (a.ms - b.ms) || (a.order - b.order));
}
