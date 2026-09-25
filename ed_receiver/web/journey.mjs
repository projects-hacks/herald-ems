import { esc, formatValue, hhmm } from './view.mjs';

/** Only the confirmed history actually delivered in a full sync; never fetch vehicle state. */
export function journeyGroups(timeline) {
  const vitals = new Map(), care = [];
  for (const point of timeline ?? []) {
    if (point.k.startsWith('vitals.') && typeof point.v === 'number') {
      if (!vitals.has(point.k)) vitals.set(point.k, []);
      vitals.get(point.k).push(point);
    }
    if (point.k === 'meds.given' || point.k === 'procedures.done') care.push(point);
  }
  return { vitals: [...vitals].filter(([, points]) => points.length > 1), care };
}

export function renderJourney(incident, keys) {
  const { vitals, care } = journeyGroups(incident.timeline);
  const at = (point) => {
    const date = new Date(point.o ?? point.t);
    return Number.isFinite(date.getTime()) ? hhmm(date) : 'Time unavailable';   // local 24-hour, like every other time here
  };
  const pointText = (point) => `${formatValue(point.v)}${keys[point.k]?.unit ? ` ${keys[point.k].unit}` : ''}`;
  return `<section class="card journey"><h2>Journey received from the ambulance</h2>
    <p class="muted">Confirmed history from the latest full sync. Newer critical fields above may have arrived separately.</p>
    ${vitals.length ? vitals.map(([key, points]) => `<div class="journey-trend"><h3>${esc(keys[key]?.label ?? key)}</h3><ol>${points.map(point => `<li><strong>${esc(pointText(point))}</strong><time>${esc(at(point))}</time></li>`).join('')}</ol></div>`).join('') : '<p>No confirmed trend history received yet.</p>'}
    <h3>Recorded medications and procedures</h3>${care.length ? `<ol>${care.map(point => `<li>${esc(pointText(point))} <span class="muted">· recorded ${esc(at(point))}</span></li>`).join('')}</ol>` : '<p>No confirmed care events received yet.</p>'}</section>`;
}
